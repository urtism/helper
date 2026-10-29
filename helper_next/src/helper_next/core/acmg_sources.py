"""On-demand access to HELPER sources. Scientific qualification stays in the engine."""
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

    def __init__(self, gene_database=None, population_database=None, transcript_provider=None, mechanism_fetch=None, mapping_registry=None):
        self.gene_database = gene_database
        self.population_database = population_database
        self.transcript_provider = transcript_provider or TranscriptReferenceProvider()
        self.mechanism_fetch = mechanism_fetch
        self.mapping_registry = mapping_registry

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
            raw = copy.deepcopy(attached) if attached is not None else gnomad_frequency.cached_variant(
                *args, database=self.population_database)
            if raw is None and fetch:
                raw = gnomad_frequency.lookup_variant(*args, database=self.population_database)
            status = "CACHED" if raw and raw.get("cache") != "miss" else "AVAILABLE"
            if raw and raw.get("status") == "unavailable":
                # The legacy client merges transport and parsing failures. Its
                # generic error is not proof that the source was unreachable.
                status = "ERROR" if raw.get("error") else "AVAILABLE"
            elif raw and raw.get("status") == "unsupported":
                status = "ERROR"
            return {"source_id": "gnomad_frequency", "status": status, "data": raw,
                    "release": (raw or {}).get("release"),
                    "acquired_at": (raw or {}).get("retrieved_at"),
                    "freshness": "NOT_RECORDED", "cache_policy": "existing allele/release cache"}
        except (URLError, TimeoutError, ConnectionError):
            return self._failure("gnomad_frequency", "UNREACHABLE")
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
