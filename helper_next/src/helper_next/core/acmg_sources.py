"""On-demand access to HELPER's existing public biological data sources."""
import copy
import os
import sqlite3
import time
from pathlib import Path
from urllib.error import URLError

from helper_variants import gene_phenotype, gnomad_frequency, source_registry
from helper_next.core.acmg_transcripts import TranscriptReferenceProvider


class SourceManager:
    """Use the existing public-data caches; never cache a clinical workspace here."""

    def __init__(self, gene_database=None, population_database=None, transcript_provider=None, mechanism_fetch=None, mapping_registry=None,
                 vcep_database=None):
        self.gene_database = gene_database
        self.population_database = population_database
        self.transcript_provider = transcript_provider or TranscriptReferenceProvider()
        self.mechanism_fetch = mechanism_fetch
        self.mapping_registry = mapping_registry
        self.vcep_database = vcep_database

    def vcep(self, identity, *, variation_ids=(), caids=(), hgvs=(), allele_identity=None, record=None):
        """External expert assertions only; never an ACMG decision or fetch."""
        context = dict(identity, variation_ids=variation_ids, caids=caids, hgvs=hgvs, allele_identity=allele_identity)
        return self.vcep_batch([context], record=record)[0]

    def vcep_batch(self, contexts, *, record=None, checksum_reference=True):
        from helper_next.core.biological_identity import allele_refs_batch, ALLELE_CONTRACT_VERSION
        from helper_variants.clingen_vcep_adapter import lookup_batch

        contexts = [dict(context) for context in contexts]
        genomic_fields = ("assembly", "chromosome", "position", "reference", "alternate")
        for context in contexts:
            attached = context.get("allele_identity")
            if attached is not None and (attached.get("contract_version") != ALLELE_CONTRACT_VERSION
                    or any(attached.get("original", {}).get(key) != context.get(key) for key in genomic_fields)):
                context["allele_identity"] = None
        pending = [index for index, context in enumerate(contexts)
                   if context.get("allele_identity") is None
                   and isinstance(context.get("reference"), str) and len(context["reference"]) == 1
                   and isinstance(context.get("alternate"), str) and len(context["alternate"]) == 1]
        qualified = allele_refs_batch([tuple(contexts[index].get(key) for key in genomic_fields)
                                       for index in pending], record=record, checksum_reference=checksum_reference)
        for index, identities in zip(pending, qualified):
            contexts[index]["allele_identity"] = identities[0]
        return lookup_batch(contexts, self.vcep_database)

    def ontology_registry(self, store=None):
        if self.mapping_registry is None:
            from helper_next.core.acmg_ontology import OntologyMappingRegistry
            self.mapping_registry = OntologyMappingRegistry(store)
        return self.mapping_registry

    def mechanism_association_inventory(self):
        return gene_phenotype.mechanism_association_inventory(self.gene_database)

    def transcript(self, transcript, assembly, fetch=None):
        return self.transcript_provider.get(transcript, assembly,
                                            fetch=os.environ.get("HELPER_TRANSCRIPT_FETCH") == "1" if fetch is None else fetch)

    def gene_transcripts(self, gene, assembly, fetch=None):
        return self.transcript_provider.gene_transcripts(gene, assembly,
                                                        fetch=os.environ.get("HELPER_TRANSCRIPT_FETCH") == "1" if fetch is None else fetch)

    def mechanism_revision(self):
        """Cheap local invalidation token, including in-place SQLite/WAL updates."""
        path = Path(self.gene_database or gene_phenotype.cache_path())
        tokens = []
        for candidate in (path, Path(str(path) + "-wal")):
            if candidate.is_file():
                stat = candidate.stat()
                tokens.append((stat.st_ino, stat.st_size, stat.st_mtime_ns))
        return tokens

    def mechanism_records(self, gene_id, symbol="", sources=None, refresh=False, timeout=15):
        """Reuse indexed datasets; only the existing targeted gnomAD fetch can run.

        Refreshing full-dataset sources means rereading their current local
        index. Its own source age is retained, never relabeled as a remote sync.
        """
        selected = set(sources or ("g2p", "gencc", "clingen_dosage", "gnomad", "clinvar"))
        remote_error = None
        remote_fetch_ms = None
        allow_fetch = self.mechanism_fetch if self.mechanism_fetch is not None else os.environ.get("HELPER_MECHANISM_FETCH") == "1"
        if refresh and "gnomad" in selected and symbol and allow_fetch:
            started = time.perf_counter()
            try:
                gene_phenotype.refresh_gnomad_constraint(symbol, database=self.gene_database, timeout=timeout)
            except (OSError, ValueError, RuntimeError, sqlite3.Error) as exc:
                remote_error = "UNREACHABLE" if isinstance(exc, (URLError, TimeoutError, ConnectionError)) else "ERROR"
            finally:
                remote_fetch_ms = (time.perf_counter() - started) * 1000
        try:
            result = gene_phenotype.mechanism_source_records(gene_id, symbol, database=self.gene_database, sources=selected)
        except (OSError, sqlite3.Error, ValueError):
            from helper_next.core.analysis_history import now
            result = {s: {"source": s, "status": "ERROR", "records": [], "retrieved_at": now(),
                          "limitations": ["Existing public source index could not be read"]} for s in selected}
        if remote_error:
            result["gnomad"].update(status=remote_error, records=[], refresh_scope="TARGETED_REMOTE")
        elif refresh and "gnomad" in selected and symbol and allow_fetch:
            result["gnomad"]["refresh_scope"] = "TARGETED_REMOTE"
        if remote_fetch_ms is not None:
            result["gnomad"]["remote_fetch_ms"] = remote_fetch_ms
        return result

    def catalog(self):
        """Explicit local discovery, without HTTP probes or synchronization."""
        result = source_registry.catalog(gene_database=self.gene_database,
                                         gnomad_frequency_database=self.population_database)
        states = {"synchronized": "CACHED", "bundled": "AVAILABLE", "on_demand": "AVAILABLE",
                  "stale": "STALE", "unavailable": "ERROR"}
        return [dict(item, availability=states[item["status"]]) for item in result["sources"]]

    def population(self, identity, attached=None, fetch=False):
        """Fetch only when explicitly requested; offline is the normal builder policy."""
        args = [identity[k] for k in ("assembly", "chromosome", "position", "reference", "alternate")]
        try:
            try:
                key = gnomad_frequency.cache_key(*args)
            except (TypeError, ValueError):
                return {"source_id": "gnomad_frequency", "status": "UNSUPPORTED",
                        "data": None, "freshness": "UNKNOWN"}
            if attached is not None and not gnomad_frequency._matches_context(attached, key):
                attached = None
            raw = copy.deepcopy(attached) if attached is not None else gnomad_frequency.cached_variant(
                *args, database=self.population_database)
            if raw is None and fetch:
                raw = gnomad_frequency.lookup_variant(*args, database=self.population_database)
            if raw is not None:
                raw = gnomad_frequency._access_metadata(raw)
            status = (raw or {}).get("availability", "NOT_QUERIED")
            return {"source_id": "gnomad_frequency", "status": status, "data": raw,
                    "release": (raw or {}).get("release"),
                    "acquired_at": (raw or {}).get("retrieved_at"),
                    "freshness": (raw or {}).get("freshness", "UNKNOWN"),
                    "last_error": (raw or {}).get("last_error"),
                    "cache_policy": "existing allele/release cache"}
        except (URLError, TimeoutError, ConnectionError):
            return self._failure("gnomad_frequency", "ERROR")
        except (OSError, sqlite3.Error, ValueError):
            return self._failure("gnomad_frequency", "ERROR")

    def gene_disease(self, symbol, gene_id):
        try:
            raw = gene_phenotype.query_gene(symbol, gene_id, database=self.gene_database)
            cache = raw.get("cache", {})
            status = "ERROR" if cache.get("status") == "invalid" else (
                "STALE" if cache.get("stale") else "CACHED" if cache.get("status") == "ready" else "AVAILABLE")
            return {"source_id": "gene_disease", "status": status, "data": raw,
                    "release": None, "acquired_at": cache.get("updated_at"),
                    "limitations": ["Cache schema/date is not an upstream scientific release"]}
        except (URLError, TimeoutError, ConnectionError):
            return self._failure("gene_disease", "UNREACHABLE")
        except (OSError, sqlite3.Error, ValueError):
            return self._failure("gene_disease", "ERROR")

    @staticmethod
    def _failure(source_id, status):
        return {"source_id": source_id, "status": status, "data": None,
                "error": {"code": "SOURCE_" + status, "message": "Requested source could not be read"}}
