"""Bulk orchestration over local source indexes and the Task 27A resolver."""
import json
import copy
import logging
import re
import sqlite3
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone

from helper_variants import gene_phenotype
from helper_next.core import acmg_mechanism_normalizer as norm
from helper_next.core.acmg_client import digest
from helper_next.core.acmg_mechanism_models import SourcePacket
from helper_next.core.acmg_mechanisms import MechanismEvidenceCache
from helper_next.core.acmg_mechanism_store import record_reference


logger = logging.getLogger(__name__)
BULK_VERSION = "mechanism-bulk-2.0"


def log(event, **fields):
    logger.info(json.dumps({"event": "mechanism_bulk_" + event, **fields}, sort_keys=True))


def disease_order(identifier):
    return ({"MONDO": 0, "OMIM": 1, "ORPHA": 2}.get(identifier.split(":")[0], 3), identifier)


def dataset_fingerprints(tables):
    """Reproducible acquired projections, explicitly distinct from upstream releases."""
    return {source: {"sha256": digest(sorted(digest(row)["value"] for row in tables.get(table, [])))["value"],
                     "records": len(tables.get(table, [])), "scope": "LOCAL_INDEXED_ROWS_V1", "table": table}
            for source, table in (("g2p", "g2p_records"), ("gencc", "assertions"),
                                  ("orphadata", "orpha_aliases"), ("clingen_dosage", "clingen_dosage"),
                                  ("gnomad", "gnomad_constraints"))}


def build_inventory(sources):
    registry = sources.ontology_registry().pin()
    versions = MechanismEvidenceCache._versions(registry)
    inventory = sources.mechanism_association_inventory()
    metadata, tables = inventory["metadata"], inventory["tables"]
    source_status, problems = {}, []
    try:
        acquired = datetime.fromisoformat(metadata.get("updated_at", "").replace("Z", "+00:00"))
        if acquired.tzinfo is None:
            raise ValueError("Unknown acquisition timezone")
        stale = datetime.now(timezone.utc) - acquired > gene_phenotype.CACHE_MAX_AGE
    except ValueError:
        acquired, stale = None, True
    for source, table, url in (("g2p", "g2p_records", "g2p_source_url"), ("gencc", "assertions", "source_url")):
        status = ("MISSING_INDEX" if not inventory["exists"] else "INCOMPATIBLE_SCHEMA" if metadata.get("schema_version") != gene_phenotype.SCHEMA_VERSION
                  else "NOT_SYNCHRONIZED" if table not in tables or not metadata.get(url) or acquired is None
                  else "EMPTY_INDEX" if not tables[table] else "STALE" if stale else "READY")
        source_status[source] = {"status": status, "records": len(tables.get(table, [])),
                                 "dataset_version": None, "index_acquired_at": metadata.get("updated_at"), "source_url": metadata.get(url)}
        if status not in ("READY", "STALE"):
            problems.append({"source": source, "code": status})
    report = {"source_index": inventory["database"], "source_status": source_status,
              "source_records": {s: v["records"] for s, v in source_status.items()},
              "source_associations": {"g2p": 0, "gencc": 0}, "unique_associations": 0,
              "normalized_source_associations": {"g2p": 0, "gencc": 0}, "cross_source_associations": 0,
              "invalid_records": 0, "invalid_record_reasons": {}, "invalid_record_examples": [],
              "ambiguous_mapping_associations": 0, "source_problems": problems,
              "index_stale": stale, "scope": "SYNCHRONIZED_LOCAL_INDEX_ONLY", "global_dataset_completeness": "NOT_ATTESTED",
              "dataset_versions": {s: None for s in ("g2p", "gencc", "clingen_dosage", "gnomad")},
              "gencc_record_versions": sorted({str(r.get("version_number")) for r in tables.get("assertions", [])}),
              "dataset_fingerprints": dataset_fingerprints(tables),
              "ontology_registry": versions["ontology_registry"], "mapping_status_counts": {},
              "warnings": ["Scientific dataset releases are not recorded by the existing local index",
                           "Completeness refers only to valid associations in the enumerated local indexes"]}
    if problems:
        return {"report": report, "associations": [], "hash": None}
    if stale:
        report["warnings"].append("Source indexes are stale; population does not synchronize upstream datasets")
    # Reuse the exact-mapping rows already imported by the existing adapter.
    links_by_id, links_by_orpha = defaultdict(list), defaultdict(list)
    for link in tables.get("orpha_aliases", []):
        links_by_id[link["identifier"]].append(link["orpha_id"])
        links_by_orpha[link["orpha_id"]].append(dict(link, source_url=metadata.get("orphadata_source_url")))
    records_by_gene, candidates = defaultdict(list), []
    per_source, invalid = {"g2p": set(), "gencc": set()}, Counter()
    for source, table in (("g2p", "g2p_records"), ("gencc", "assertions")):
        packet = SourcePacket(source=source, status="AVAILABLE", retrieved_at=metadata["updated_at"])
        for original in tables[table]:
            record_id = original.get("g2p_id") or original.get("sgc_id")
            try:
                row = dict(original)
                info = norm.describe(source, row)
                gene = norm.curie(info["gene_id"] or "", gene=True)
                if not re.fullmatch(r"HGNC:[0-9]+", gene):
                    raise ValueError("MISSING_HGNC_ID")
                linked = {o for d in info["disease_ids"] for o in links_by_id.get(d, [])}
                row["disease_mappings"] = sorted([link for o in linked for link in links_by_orpha[o]], key=lambda a: (a["identifier"], a["orpha_id"]))
                ref = record_reference(packet, row)
                records_by_gene[gene].append((packet, row, ref))
                if not info["disease_ids"]:
                    raise ValueError("MISSING_DISEASE_ID")
                primary = row.get("disease_curie") or row.get("disease_mim") or row.get("disease_original_curie")
                disease = norm.curie(primary)
                request = norm.identity(gene, disease, info["original_inheritance"])
                per_source[source].add(norm.association_key(request))
                candidates.append((request, row, info["original_inheritance"], source))
            except (ValueError, KeyError, TypeError):
                reason = "INVALID_GENE_DISEASE_ID_OR_SOURCE_RECORD"
                if not original.get("gene_curie"):
                    reason = "MISSING_HGNC_ID"
                elif not any(original.get(k) for k in ("disease_curie", "disease_mim", "disease_original_curie")):
                    reason = "MISSING_DISEASE_ID"
                invalid[reason] += 1
                if len(report["invalid_record_examples"]) < 20:
                    report["invalid_record_examples"].append({"source": source, "record_id": record_id, "reason": reason})
    contexts = defaultdict(list)
    for source, table in (("clingen_dosage", "clingen_dosage"), ("gnomad", "gnomad_constraints")):
        for row in tables.get(table, []):
            contexts[row["gene_symbol"].upper()].append((source, row))
    mapped, mappings = {}, {}
    normalized_source = {"g2p": set(), "gencc": set()}
    for request, row, original_requirement, source in candidates:
        component_key = (request.gene_id, request.disease_id)
        if component_key not in mappings:
            mappings[component_key] = norm.mapping(request, records_by_gene[request.gene_id], registry)
        aliases, edges, ambiguous = mappings[component_key]
        canonical = min(aliases, key=disease_order)
        canonical_request = norm.identity(request.gene_id, canonical, original_requirement)
        key = norm.association_key(canonical_request)
        normalized_source[source].add(key)
        if key in mapped:
            mapped[key]["sources"] = sorted(set(mapped[key]["sources"]) | {source})
            mapped[key]["original_disease_ids"] = sorted(set(mapped[key]["original_disease_ids"]) | {request.disease_id})
            continue
        records = records_by_gene[request.gene_id]
        pertinent_mapping = {e["source_record_ref"] for e in edges}
        relevant = [r for p, r, ref in records if not norm.describe(p.source, r)["disease_ids"]
                    or aliases.intersection(norm.describe(p.source, r)["disease_ids"]) or ref in pertinent_mapping]
        symbols = sorted({r.get("gene_symbol") for _, r, _ in records if r.get("gene_symbol")})
        context_records = [context for symbol in symbols for context in contexts.get(symbol.upper(), [])]
        input_hash = digest({"rows": sorted(digest(r)["value"] for r in relevant), "context": sorted(digest(c)["value"] for c in context_records),
                             "versions": versions})["value"]
        mapped[key] = {"key": key, "gene": request.gene_id, "disease": canonical,
                       "allelic_requirement": request.allelic_requirement, "resolver_requirement": original_requirement,
                       "symbol": symbols[0] if len(symbols) == 1 else None,
                       "disease_name": row.get("disease_name") or row.get("disease_title") or None,
                       "mapping_ambiguous": ambiguous, "input_hash": input_hash,
                       "original_disease_ids": [request.disease_id],
                       "mapping_status": "AMBIGUOUS_MAPPING" if ambiguous else "VERIFIED_EXACT" if len(aliases) > 1 else "NO_VERIFIED_MAPPING",
                       "mapping_uncertainty": sorted({e["verification_status"] for e in edges} - {"VERIFIED_EXACT", "IDENTITY"})}
        mapped[key]["sources"] = [source]
    associations = sorted(mapped.values(), key=lambda a: (a["gene"], disease_order(a["disease"]), a["allelic_requirement"]))
    report.update(source_associations={s: len(rows) for s, rows in per_source.items()}, unique_associations=len(associations),
                  normalized_source_associations={s: len(keys) for s, keys in normalized_source.items()},
                  cross_source_associations=len(normalized_source["g2p"] & normalized_source["gencc"]),
                  invalid_records=sum(invalid.values()), invalid_record_reasons=dict(invalid),
                  ambiguous_mapping_associations=sum(a["mapping_ambiguous"] for a in associations))
    report["mapping_status_counts"] = dict(Counter(a["mapping_status"] for a in associations))
    report["mapping_uncertainty_counts"] = dict(Counter(status for a in associations for status in a["mapping_uncertainty"]))
    if registry.manifest()["status"] == "UNAVAILABLE":
        report["warnings"].append("Ontology registry unavailable: identity-only scope; no cross-reference propagation")
    fingerprint = digest({"version": BULK_VERSION, "rows": {s: sorted(digest(r)["value"] for r in tables[t]) for s, t in (("g2p", "g2p_records"), ("gencc", "assertions"))},
                          "mapping_rows": tables.get("orpha_aliases", []), "metadata": metadata,
                          "versions": versions})["value"]
    return {"report": report, "associations": associations, "hash": fingerprint}


class BulkPopulation:
    def __init__(self, cache=None):
        self.cache = cache or MechanismEvidenceCache()
        self.store = self.cache.store

    def entry_status(self, association):
        request = norm.identity(association["gene"], association["disease"], association["resolver_requirement"])
        baseline = self.store.bulk_baseline(association["key"])
        current = self.store.peek(association["key"])
        unchanged = baseline and current and baseline["input_hash"] == association["input_hash"] and baseline["snapshot_id"] == current.snapshot_id
        state = self.cache.entry_status(request, ignore_index_revision=bool(unchanged))
        state["input_changed"] = bool(baseline and baseline["input_hash"] != association["input_hash"])
        state["verified_input"] = bool(unchanged)
        state["stale"] = state["stale"] or (state["exists"] and state["input_changed"])
        return state

    def report(self, run_id=None):
        run = self.store.bulk_run(run_id)
        report = {"cache": self.store.statistics(), "run_id": None, "status": "NOT_STARTED"}
        if not run:
            return report
        items = self.store.bulk_items(run["run_id"])
        summaries = [i["summary"] for i in items if i["summary"]]
        statuses = Counter(i["status"] for i in items)
        unavailable = Counter()
        for summary in summaries:
            unavailable.update(summary.get("sources_unavailable", {}))
        report.update(run["inventory_report"], run_id=run["run_id"], status=run["status"], planned=len(items),
                      processed=sum(i["attempts"] > 0 for i in items), successful=statuses["SUCCESS"], errors=statuses["ERROR"],
                      remaining=sum(statuses[s] for s in ("PENDING", "RUNNING", "ERROR")),
                      matrices_saved=sum(bool(s.get("snapshot_id")) for s in summaries),
                      matrices_created=sum(s.get("created", False) for s in summaries), matrices_updated=sum(s.get("updated", False) for s in summaries),
                      matrices_with_direct_assertion=sum(s.get("direct", False) for s in summaries),
                      matrices_context_only=sum(s.get("context_only", False) for s in summaries),
                      unresolved_associations=sum(s.get("unresolved", False) for s in summaries),
                      mapping_ambiguous=sum(s.get("mapping_ambiguous", False) for s in summaries),
                      sources_unavailable=dict(unavailable), snapshots_created=self.store.bulk_snapshot_count(run["run_id"]),
                      error_examples=[{"association_key": i["association_key"], "code": i["error_code"]} for i in items if i["status"] == "ERROR"][:20],
                      elapsed_seconds=run["elapsed_seconds"], options=run["options"])
        report["local_population_complete"] = (not report["remaining"] and not report["invalid_records"] and not report["options"]["refresh_stale"])
        return report

    def run(self, dry_run=False, limit=None, resume=False, refresh_stale=False, offline=False):
        if offline and self.cache.sources.mechanism_fetch is not False:
            local = copy.copy(self.cache)
            local.sources = copy.copy(self.cache.sources)
            local.sources.mechanism_fetch = False
            return BulkPopulation(local).run(dry_run, limit, resume, refresh_stale, offline)
        started = time.perf_counter()
        inventory = build_inventory(self.cache.sources)
        preflight = dict(inventory["report"], status="DRY_RUN" if dry_run else "PREFLIGHT_FAILED",
                         cache=self.store.statistics(), processed=0, matrices_saved=0, snapshots_created=0)
        if inventory["report"]["source_problems"]:
            return dict(preflight, status="PREFLIGHT_FAILED", elapsed_seconds=time.perf_counter() - started)
        if limit is not None and limit < 1:
            raise ValueError("limit must be a positive integer")
        associations = inventory["associations"]
        if refresh_stale:
            associations = [a for a in associations if (lambda state: state["exists"] and state["stale"])(self.entry_status(a))]
        if dry_run:
            if resume:
                previous = self.store.bulk_run()
                if not previous or previous["inventory_hash"] != inventory["hash"]:
                    raise ValueError("No resumable run matches the current local inventory")
                associations = [i["association"] for i in self.store.bulk_items(previous["run_id"]) if i["status"] != "SUCCESS"]
            return dict(preflight, eligible=len(associations), to_process=min(limit, len(associations)) if limit else len(associations),
                        inventory_hash=inventory["hash"], elapsed_seconds=time.perf_counter() - started)
        options = {"offline": bool(offline), "refresh_stale": bool(refresh_stale), "bulk_version": BULK_VERSION}
        with self.store.refresh_lock("mechanism-bulk-population", timeout=1) as token:
            self.store.renew_lease("mechanism-bulk-population", token, max(300, self.cache.timeout * 4 + 120))
            previous = self.store.bulk_run() if resume else None
            if resume:
                if not previous:
                    raise ValueError("No bulk population run is available to resume")
                if previous["inventory_hash"] != inventory["hash"]:
                    raise ValueError("Local source inventory changed; start --populate without --resume to create an updated plan")
                if previous["options"] != options:
                    raise ValueError("Resume requires the original --offline/--refresh-stale options")
                run_id = previous["run_id"]
            else:
                run_id = self.store.create_bulk_run(inventory["hash"], inventory["report"], associations, options)
            self.store.finish_bulk_run(run_id, "RUNNING", 0)
            log("started", run_id=run_id, resume=resume, planned=len(associations))
            attempted = 0
            try:
                revision = self.cache.sources.mechanism_revision()
                for item in self.store.bulk_items(run_id):
                    if item["status"] == "SUCCESS":
                        continue
                    if limit is not None and attempted >= limit:
                        break
                    if self.cache.sources.mechanism_revision() != revision:
                        raise ValueError("Local source index changed during population; create a new plan")
                    if self.cache._versions(self.cache.registry)["ontology_registry"] != inventory["report"]["ontology_registry"]:
                        raise ValueError("Ontology registry changed during population; create a new plan")
                    self.store.renew_lease("mechanism-bulk-population", token, max(300, self.cache.timeout * 4 + 120))
                    association = item["association"]
                    self.store.begin_bulk_item(run_id, association["key"])
                    attempted += 1
                    try:
                        freshness = self.entry_status(association)
                        policy = "FORCE_REFRESH" if item["status"] == "ERROR" else "REFRESH_IF_STALE" if not freshness["exists"] or freshness["stale"] else "CACHE_ONLY"
                        with self.store.bulk_publications(run_id):
                            result = self.cache.resolve_gene_disease_mechanism(association["gene"], association["disease"],
                                association["resolver_requirement"], cache_policy=policy, symbol=association["symbol"], disease_name=association["disease_name"],
                                rebuild=not freshness["verified_input"])
                        if result.provenance["ontology_registry"] != inventory["report"]["ontology_registry"]:
                            raise ValueError("Ontology registry changed during resolution; item requires a new plan")
                        persisted = self.store.peek(association["key"])
                        if not persisted or persisted.snapshot_id != result.snapshot_id:
                            raise ValueError("Resolver did not publish the requested matrix")
                        unavailable = {s.source + ":" + s.status: 1 for s in result.source_status if s.status not in ("AVAILABLE", "NO_RECORDS")}
                        errors = [s for s in result.source_status if s.status in ("ERROR", "UNREACHABLE", "NORMALIZATION_ERROR")]
                        summary = {"snapshot_id": result.snapshot_id, "created": item["initial_snapshot_id"] is None,
                                   "updated": bool(item["initial_snapshot_id"] and item["initial_snapshot_id"] != result.snapshot_id),
                                   "direct": bool(result.direct_evidence), "context_only": not result.direct_evidence and bool(result.contextual_evidence),
                                   "unresolved": result.reconciliation_status == "UNRESOLVED", "mapping_ambiguous": "AMBIGUOUS_DISEASE_MAPPING" in result.issues,
                                   "sources_unavailable": unavailable}
                        self.store.finish_bulk_item(run_id, association["key"], summary, "SOURCE_REFRESH_FAILED" if errors else None)
                    except (OSError, sqlite3.Error, ValueError, KeyError, TypeError) as exc:
                        self.store.finish_bulk_item(run_id, association["key"], {}, type(exc).__name__)
                        log("item_error", run_id=run_id, association_key=association["key"], code=type(exc).__name__)
                    if not offline:
                        revision = self.cache.sources.mechanism_revision()  # Targeted constraint refresh can update the local index.
                    log("progress", run_id=run_id, processed_in_invocation=attempted)
                items = self.store.bulk_items(run_id)
                pending = any(i["status"] in ("PENDING", "RUNNING") for i in items)
                failed = any(i["status"] == "ERROR" for i in items)
                self.store.finish_bulk_run(run_id, "LIMITED" if pending else "COMPLETED_WITH_ERRORS" if failed else "COMPLETED", time.perf_counter() - started)
            except BaseException:
                self.store.finish_bulk_run(run_id, "INTERRUPTED", time.perf_counter() - started)
                log("interrupted", run_id=run_id)
                raise
        report = self.report(run_id)
        report["processed_in_invocation"] = attempted
        return report
