"""Lazy public-data mechanism resolver over the existing Source Manager."""
import json
import logging
import math
import os
import sqlite3
import time
from datetime import datetime, timezone

from pydantic import ValidationError

from helper_next.core import acmg_mechanism_normalizer as norm
from helper_next.core.acmg_client import digest
from helper_next.core.acmg_mechanism_models import SOURCES, SourcePacket, SourceState
from helper_next.core.acmg_mechanism_store import MechanismStore, json_text, record_reference
from helper_next.core.acmg_sources import SourceManager


logger = logging.getLogger(__name__)


def log(event, **fields):
    logger.info(json_text({"event": "mechanism_" + event, **fields}))


class MechanismEvidenceCache:
    def __init__(self, sources=None, database=None, ttl_seconds=None, negative_ttl=3600, error_ttl=60, timeout=None, clock=None):
        self.sources = sources or SourceManager()
        self.store = MechanismStore(database)
        self.registry = self.sources.ontology_registry(self.store)
        self.sources.mapping_registry = self.registry
        configured = json.loads(os.environ.get("HELPER_MECHANISM_TTL_JSON", "{}")) if ttl_seconds is None else ttl_seconds
        if not isinstance(configured, dict) or set(configured) - set(SOURCES):
            raise ValueError("Mechanism TTL policy must map supported source names to seconds")
        self.ttl = {s: float(configured.get(s, 30 * 86400 if s == "gnomad" else 7 * 86400)) for s in SOURCES}
        self.negative_ttl, self.error_ttl = float(negative_ttl), float(error_ttl)
        self.timeout = float(os.environ.get("HELPER_MECHANISM_TIMEOUT", "15") if timeout is None else timeout)
        if any(not math.isfinite(v) or v <= 0 for v in (*self.ttl.values(), self.negative_ttl, self.error_ttl, self.timeout)):
            raise ValueError("Mechanism cache TTLs/timeouts must be finite positive values")
        self.clock = clock or time.time

    @staticmethod
    def _versions(registry=None):
        from helper_next.core.acmg_ontology import OntologyMappingRegistry
        manifest = (registry or OntologyMappingRegistry()).manifest()
        return {"normalization_version": norm.NORMALIZATION_VERSION,
                "reconciliation_version": norm.RECONCILIATION_VERSION, "mapping_version": norm.MAPPING_VERSION,
                "ontology_registry": {k: manifest[k] for k in ("registry_id", "registry_version", "policy_version", "source_version", "dataset_fingerprint", "status")},
                "rules": {"candidate_policy": "Explicit G2P molecular-mechanism assertion with demonstrated gene/disease scope",
                          "inheritance_policy": "Lexical aliases and published qualified G2P/HPO crosswalk; generic mono/biallelic remain separate",
                          "inheritance_crosswalk": norm.INHERITANCE_CROSSWALK,
                          "mapping_policy": "Only registry-qualified single-namespace-cardinality exact matches; preserve rejected cross-references; primary source disease anchors assertions",
                          "conflict_policy": "Distinct LoF/GoF/DN assertions in the same exact scope; preserve all hypotheses",
                          "independence_policy": "Shared origin references retained; no voting, counting, scores or inference from variant classes"}}

    def _state_models(self, rows):
        states = []
        for source in SOURCES:
            row = rows.get(source)
            packet = SourcePacket.parse_raw(row["payload"]) if row and row.get("payload") else None
            states.append(SourceState(source=source, status=row["status"] if row else "CACHE_MISS",
                stale=not row or self.clock() >= row["expires_at"] or bool(packet and packet.stale) or bool(row.get("error_code")),
                checked_at=datetime.fromtimestamp(row["checked_at"], timezone.utc).isoformat() if row else None,
                source_updated_at=packet.source_updated_at if packet else None,
                dataset_version=packet.dataset_version if packet else None,
                source_url=packet.source_url if packet else None, etag=packet.etag if packet else None,
                last_modified=packet.last_modified if packet else None,
                refresh_scope=packet.refresh_scope if packet else "LOCAL_INDEX", error_code=row.get("error_code") if row else None,
                limitations=packet.limitations if packet else []))
        return states

    def _overlay(self, cached, rows, failed=False):
        states = self._state_models(rows)
        warnings = list(cached.warnings)
        if failed:
            warnings.append("Last complete snapshot retained: a source refresh or normalization failed; no partial replacement performed")
        if any(s.stale for s in states):
            warnings.append("One or more public source records are stale; upstream freshness is not guaranteed")
        issues = set(cached.issues)
        if any(s.status in ("UNREACHABLE", "ERROR", "NORMALIZATION_ERROR") for s in states):
            issues.add("SOURCE_UNAVAILABLE")
        return cached.copy(update={"source_status": states, "warnings": warnings, "issues": sorted(issues)})

    def _records(self, rows):
        records = []
        for source in SOURCES:
            state = rows.get(source)
            if not state or not state.get("payload"):
                continue
            packet = SourcePacket.parse_raw(state["payload"])
            for row in packet.records:
                ref = record_reference(packet, row)
                try:
                    original = self.store.source_record(ref)
                    packet_for_record = packet.copy(update={"retrieved_at": original["retrieved_at"]})
                except KeyError:
                    packet_for_record = packet
                records.append((packet_for_record, row, ref))
        return records

    def entry_status(self, request, ignore_index_revision=False):
        """Technical freshness only; read-only and without source acquisition."""
        request = request.copy(update={"disease_id": self.registry.canonical(request.disease_id)})
        cached = self.store.peek(norm.association_key(request))
        if cached is None:
            return {"exists": False, "stale": False, "snapshot_id": None}
        states = self.store.peek_states(request.gene_id)
        stale = any(cached.provenance.get(k) != v for k, v in self._versions(self.registry).items())
        revision = None if ignore_index_revision else json_text(self.sources.mechanism_revision())
        for source in SOURCES:
            row = states.get(source)
            if not row:
                stale = True
                continue
            if (self.clock() >= row["expires_at"] or row.get("error_code")
                    or (not ignore_index_revision and row["local_revision"] != revision)):
                stale = True
        return {"exists": True, "stale": bool(stale), "snapshot_id": cached.snapshot_id}

    def resolve_gene_disease_mechanism(self, gene, disease, allelic_requirement=None,
                                      cache_policy="REFRESH_IF_STALE", snapshot_id=None, symbol=None, disease_name=None, rebuild=False):
        lookup_started = time.perf_counter()
        registry = self.registry.pin()
        request = norm.identity(gene, disease, allelic_requirement, symbol, disease_name)
        if cache_policy not in ("CACHE_ONLY", "REFRESH_IF_STALE", "FORCE_REFRESH", "SNAPSHOT"):
            raise ValueError("Unknown mechanism cache policy")
        if cache_policy == "SNAPSHOT":
            if not snapshot_id:
                raise ValueError("SNAPSHOT policy requires snapshot_id")
            result = self.store.snapshot(snapshot_id)
            if (result.identity.gene_id != request.gene_id or request.disease_id not in {result.identity.disease_id, *result.identity.disease_aliases}
                    or norm.allelic(result.identity.allelic_requirement.removeprefix("OTHER:")) != request.allelic_requirement):
                raise ValueError("Snapshot belongs to a different gene-disease/allelic-requirement association")
            log("snapshot_replay", snapshot_id=snapshot_id, lookup_ms=(time.perf_counter() - lookup_started) * 1000)
            return result
        if snapshot_id:
            raise ValueError("snapshot_id is only accepted with SNAPSHOT policy")
        request = request.copy(update={"disease_id": registry.canonical(request.disease_id)})
        key = norm.association_key(request)
        cached, observed = self.store.current(key), self.store.states(request.gene_id)
        revision = json_text(self.sources.mechanism_revision()) if cache_policy != "CACHE_ONLY" else None
        versions_changed = bool(cached and any(cached.provenance.get(k) != v for k, v in self._versions(registry).items()))
        due = [s for s in SOURCES if s not in observed or (cache_policy != "CACHE_ONLY" and (
            self.clock() >= observed[s]["expires_at"] or observed[s]["local_revision"] != revision))]
        if cached and not rebuild and cache_policy != "FORCE_REFRESH" and not versions_changed and (cache_policy == "CACHE_ONLY" or not due):
            log("cache_hit", key=key, lookup_ms=(time.perf_counter() - lookup_started) * 1000)
            return self._overlay(cached, observed, any(r.get("error_code") for r in observed.values()))
        log("cache_miss" if not cached else "invalidation", key=key, versions_changed=versions_changed,
            lookup_ms=(time.perf_counter() - lookup_started) * 1000)
        with self.store.refresh_lock(request.gene_id, timeout=max(30, self.timeout * 4 + 10)):
            # The winner may already have refreshed this resource for another
            # request/association. FORCE_REFRESH deduplicates overlapping calls.
            cached = self.store.current(key)
            rows = self.store.states(request.gene_id)
            revision = json_text(self.sources.mechanism_revision())
            selected = [s for s in SOURCES if s not in rows or (
                cache_policy == "FORCE_REFRESH" and (s not in observed or rows[s]["checked_at"] == observed[s]["checked_at"]))
                or (cache_policy != "CACHE_ONLY" and (self.clock() >= rows[s]["expires_at"] or rows[s]["local_revision"] != revision))]
            retrieval_started = time.perf_counter()
            try:
                packets = self.sources.mechanism_records(request.gene_id, symbol or (cached.identity.gene_symbol if cached else ""),
                    sources=selected, refresh=cache_policy != "CACHE_ONLY", timeout=self.timeout) if selected else {}
            except (OSError, sqlite3.Error, ValueError, RuntimeError) as exc:
                status = "UNREACHABLE" if isinstance(exc, (OSError, TimeoutError, ConnectionError)) else "ERROR"
                packets = {s: {"source": s, "status": status, "records": [],
                               "retrieved_at": datetime.now(timezone.utc).isoformat()} for s in selected}
            retrieval_ms = (time.perf_counter() - retrieval_started) * 1000
            revision = json_text(self.sources.mechanism_revision())
            for source in selected:
                old = rows.get(source, {})
                state = {"source": source, "checked_at": self.clock(), "local_revision": revision,
                         "status": "ERROR", "expires_at": self.clock() + self.error_ttl,
                         "payload": old.get("payload"), "error_code": None}
                try:
                    packet = SourcePacket.parse_obj(packets[source])
                    if packet.source != source:
                        raise ValueError("Source packet identity mismatch")
                    json_text(packet.dict())  # Reject nonfinite external values before persistence.
                    record_ids = set()
                    for raw in packet.records:
                        record_id = norm.describe(source, raw)["source_record_id"]
                        if record_id in record_ids:
                            raise ValueError("Source packet has multiple current revisions for one record")
                        record_ids.add(record_id)
                        if raw.get("dataset_version") is not None and raw["dataset_version"] != packet.dataset_version:
                            raise ValueError("Mixed source dataset releases are not accepted")
                    state["status"] = packet.status
                    if packet.status in ("UNREACHABLE", "ERROR"):
                        state["error_code"] = "SOURCE_" + packet.status
                    else:
                        # Validate normalization before replacing a previously
                        # valid packet, including all applicable source fields.
                        preview = [(packet, row, record_reference(packet, row)) for row in packet.records]
                        norm.normalize(request, preview, registry)
                        state["payload"] = json_text(packet.dict())
                        ttl = self.negative_ttl if packet.status == "NO_RECORDS" else self.ttl[source]
                        if packet.status == "CACHE_MISS" or packet.stale:
                            ttl = self.error_ttl
                        state["expires_at"] = self.clock() + ttl
                except (ValidationError, ValueError, KeyError, TypeError):
                    state.update(status="NORMALIZATION_ERROR", error_code="SOURCE_NORMALIZATION_ERROR")
                rows[source] = state
                if old.get("payload") and state.get("payload") and not state["error_code"]:
                    before, after = json.loads(old["payload"]), json.loads(state["payload"])
                    if (before["records"], before.get("dataset_version")) != (after["records"], after.get("dataset_version")):
                        log("source_revision", key=key, source=source)
                log("source_error" if state["error_code"] else "refresh", key=key, source=source,
                    status=state["status"], retrieval_ms=retrieval_ms,
                    remote_fetch_ms=packets.get(source, {}).get("remote_fetch_ms"))
            failed = any(r.get("error_code") for r in rows.values())
            if failed and cached and not versions_changed:
                with self.store.connect() as db:
                    self.store.save_states(db, request.gene_id, [dict(r, source=s) for s, r in rows.items()])
                return self._overlay(cached, rows, True)
            records = self._records(rows)
            result = norm.analyze(request, records, self._state_models(rows), registry)
            result = result.copy(update={"provenance": self._versions(registry)})
            saved = self.store.publish(key, result, records, [dict(r, source=s) for s, r in rows.items()])
            if not cached or saved.snapshot_id != cached.snapshot_id:
                log("snapshot_created", key=key, snapshot_id=saved.snapshot_id, status=saved.resolution_status)
            if "CONTRADICTORY_ASSERTIONS" in saved.issues:
                log("conflict", key=key, snapshot_id=saved.snapshot_id)
            if "AMBIGUOUS_DISEASE_MAPPING" in saved.issues:
                log("mapping_ambiguous", key=key, snapshot_id=saved.snapshot_id)
            return self._overlay(saved, rows)


def resolve_gene_disease_mechanism(gene, disease, allelic_requirement=None, **kwargs):
    """Default public interface; callers may retain a cache instance for dependency injection."""
    return MechanismEvidenceCache().resolve_gene_disease_mechanism(gene, disease, allelic_requirement, **kwargs)
