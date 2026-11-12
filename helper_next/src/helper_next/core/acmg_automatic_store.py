"""Rebuildable automatic results, separate from user interpretation revisions."""
import copy
import fcntl
import json
import os
import sqlite3
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from contextlib import contextmanager
from datetime import datetime, timezone
from functools import lru_cache

from helper_next.core.acmg_digest import digest
from helper_next.core import acmg_input_revision_cache
from helper_next.core import acmg_classification_store as worksheets
from helper_next.core import acmg_pvs1_store as pvs1
from helper_next.core.acmg_cache_writer import CacheWriteError, CacheWriter, use_writer, write_batch, write_row
from helper_variants import gene_phenotype, store


_locks = [threading.RLock() for _ in range(64)]
_knowledge_locks = [threading.Lock() for _ in range(32)]


@contextmanager
def evaluation_lock(run_dir, sample_id, variant_id):
    """Coalesce the same allele across browser requests and preparation workers."""
    offset = int(digest([str(pvs1.path(run_dir).parent.resolve()), sample_id, variant_id])["value"][:8], 16) % (2 ** 31)
    with _locks[offset % len(_locks)]:
        filename = pvs1.path(run_dir).with_suffix(".automatic-{}.lock".format(offset % len(_locks)))
        filename.parent.mkdir(parents=True, exist_ok=True)
        with filename.open("a+b") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)


def gene_revision(symbol, gene_id=""):
    from helper_next.core.acmg_sources import SourceManager
    path = str(gene_phenotype.cache_path().resolve())
    stamp = json.dumps(SourceManager(mechanism_fetch=False).mechanism_revision(), sort_keys=True)
    return _gene_revision(path, stamp, symbol, gene_id if gene_id.startswith("HGNC:") else "")


@lru_cache(maxsize=128)
def _cached_knowledge(path, stamp, symbol, hgnc):
    return gene_phenotype.query_gene(symbol, hgnc, database=path)


def _knowledge(path, stamp, symbol, hgnc):
    with _knowledge_locks[hash((path, stamp, symbol, hgnc)) % len(_knowledge_locks)]:
        return _cached_knowledge(path, stamp, symbol, hgnc)


def gene_knowledge(symbol, hgnc=""):
    """Share gene facts across alleles, while keeping each context a private copy."""
    from helper_next.core.acmg_sources import SourceManager
    path = str(gene_phenotype.cache_path().resolve())
    stamp = json.dumps(SourceManager(mechanism_fetch=False).mechanism_revision(), sort_keys=True)
    data = _knowledge(path, stamp, symbol, hgnc)
    data = copy.deepcopy({key: data[key] for key in ("cache", "gene_identifiers", "g2p_records", "associations") if key in data})
    data["cache"]["refreshing"] = gene_phenotype.is_refreshing()
    if "stale" in data["cache"]:
        try:
            updated = datetime.strptime(data["cache"].get("updated_at", ""), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            data["cache"]["stale"] = (data["cache"].get("schema_version") != gene_phenotype.SCHEMA_VERSION
                                      or datetime.now(timezone.utc) - updated > gene_phenotype.CACHE_MAX_AGE)
        except ValueError:
            data["cache"]["stale"] = True
    return data


@lru_cache(maxsize=1024)
def _gene_revision(path, stamp, symbol, hgnc):
    """Unrelated genes and cache access timestamps cannot invalidate an assessment."""
    data = _knowledge(path, stamp, symbol, hgnc)
    ignored = {"cache", "updated_at", "retrieved_at", "refreshing", "stale", "database"}
    def scientific(value):
        if isinstance(value, dict):
            return {key: scientific(item) for key, item in value.items() if key not in ignored}
        if isinstance(value, list):
            return [scientific(item) for item in value]
        return value
    cache = data.get("cache", {})
    return digest([scientific(data), {key: cache.get(key) for key in (
        "status", "schema_version", "source_url", "g2p_source_url", "clingen_dosage_source_url", "orphadata_source_url")}])["value"]


def source_revision(assembly, record=None, gene_symbols=None):
    """Biological inputs only: UI, ClinVar paging and population reads are irrelevant."""
    from helper_next.core.acmg_reference import reference_record
    from helper_next.core.acmg_sources import SourceManager
    from helper_next.core.acmg_classification import VERSION
    from helper_next.core.acmg_molecular_impact import VERSION as impact_version
    from helper_next.core.acmg_splice import VERSION as splice_version
    from helper_next.core.acmg_mechanism_assessment import RULES_VERSION as mechanism_version
    from pvs1.calculator import RULESET_VERSION
    from pvs1.molecular import VERSION as molecular_version
    assembly = {"hg19": "GRCh37", "hg38": "GRCh38", "grch37": "GRCh37", "grch38": "GRCh38"}.get(assembly.lower(), assembly)
    reference, config = reference_record(assembly, record)
    tools = reference.get("tools_config", {}).get(assembly)
    candidates = [reference.get("run_config", {}).get("reference_fasta"),
                  tools.get("fasta") if isinstance(tools, dict) else None]
    files = pvs1.file_states([str(path) + suffix for path in candidates if path for suffix in ("", ".fai")])
    return digest([VERSION, RULESET_VERSION, molecular_version, impact_version, splice_version, mechanism_version,
                   config, reference.get("run_config", {}).get("reference_version"), files,
                   [gene_revision(symbol) for symbol in sorted(set(gene_symbols))] if gene_symbols is not None
                   else SourceManager(mechanism_fetch=False).mechanism_revision()])["value"]


def input_revisions(database, variant_ids):
    """Hash annotation content; reuse digests only while the index is unchanged."""
    return acmg_input_revision_cache.revisions(database, variant_ids, _calculate_input_revisions)


def _calculate_input_revisions(database, variant_ids):
    ids = sorted(set(variant_ids))
    rows = {}
    with store.connect(database) as db:
        for start in range(0, len(ids), 400):
            batch = ids[start:start + 400]
            placeholders = ",".join("?" for _ in batch)
            for row in db.execute(
                "SELECT v.id AS variant_id,v.reference_build,v.chromosome,v.position,v.reference,v.alternate,"
                "v.metadata_json AS variant_metadata,an.*,ar.resources_json FROM variants v "
                "LEFT JOIN annotations an ON an.variant_id=v.id LEFT JOIN annotation_releases ar ON ar.id=an.release_id "
                "WHERE v.id IN (" + placeholders + ") ORDER BY v.id,an.id", batch):
                annotation = dict(row)
                annotation["variant_metadata"] = biological_metadata(row["variant_metadata"])
                rows.setdefault(row["variant_id"], []).append(annotation)
    return {variant_id: digest(annotations)["value"] for variant_id, annotations in rows.items()}


def biological_metadata(value):
    data = json.loads(value) if isinstance(value, str) else value
    return {key: item for key, item in data.items() if key != "gnomad_enrichment"}


def _input_genes(database, variant_ids):
    result = {}
    ids = sorted(set(variant_ids))
    with store.connect(database) as db:
        for start in range(0, len(ids), 400):
            batch = ids[start:start + 400]
            for row in db.execute("SELECT DISTINCT variant_id,gene FROM annotations WHERE variant_id IN ("
                                  + ",".join("?" for _ in batch) + ") AND gene<>'' ORDER BY gene", batch):
                result.setdefault(row["variant_id"], []).append(row["gene"])
    return result


def _exists(db):
    return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='automatic_classifications'").fetchone()


def user_revision(run_dir):
    """Manual saves invalidate browser views; automatic cache writes do not."""
    values = []
    if run_dir and pvs1.path(run_dir).is_file():
        with sqlite3.connect(pvs1.path(run_dir).resolve().as_uri() + "?mode=ro", uri=True) as db:
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            for table in ("classification_heads", "pvs1_evaluations"):
                if table in tables:
                    values.append((table, list(db.execute("SELECT COUNT(*),MAX(saved_at) FROM " + table).fetchone())))
    return digest(values)["value"]


def load(run_dir, identity, signature):
    database = pvs1.path(run_dir)
    if not database.is_file():
        return None
    with sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True) as db:
        if not _exists(db):
            return None
        row = db.execute("SELECT result_json,snapshot_json FROM automatic_classifications WHERE identity_key=? AND signature=?",
                         (digest(identity)["value"], signature)).fetchone()
    if row is None:
        return None
    result, snapshot = json.loads(row[0]), json.loads(row[1])
    if snapshot and pvs1.needs_review(dict(signature=signature, snapshot=snapshot), signature):
        return None
    return result, snapshot


def save(run_dir, identity, signature, result, snapshot, source, inputs):
    result = copy.deepcopy(result)
    for criterion in result["assessment"]["criteria"]:
        criterion.pop("pvs1_evaluation_id", None)  # Tickets are recreated from the verified snapshot on reading.
    write_row(run_dir, (digest(identity)["value"], worksheets.variant_key(identity), json.dumps(identity, sort_keys=True), signature,
                       json.dumps(result), json.dumps(snapshot), source, inputs))


def batch_summaries(run_dir, identities, database, variant_ids, record=None):
    filename = pvs1.path(run_dir)
    if not filename.is_file():
        return {}
    keys = list(dict.fromkeys(worksheets.variant_key(identity) for identity in identities))
    rows = []
    with sqlite3.connect(filename.resolve().as_uri() + "?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        if not _exists(db):
            return {}
        for start in range(0, len(keys), 400):
            batch = keys[start:start + 400]
            rows.extend(db.execute("SELECT * FROM automatic_classifications WHERE variant_key IN ("
                                   + ",".join("?" for _ in batch) + ")", batch).fetchall())
    if not rows:
        return {}
    inputs = input_revisions(database, [variant_ids[row["variant_key"]] for row in rows if row["variant_key"] in variant_ids])
    genes = _input_genes(database, inputs)
    sources, result = {}, {}
    for row in rows:
        if row["variant_key"] not in variant_ids:
            continue
        identity = json.loads(row["identity_json"])
        assembly = identity["assembly"]
        source_key = (assembly, tuple(genes.get(variant_ids[row["variant_key"]], [])))
        if source_key not in sources:
            sources[source_key] = source_revision(assembly, record, source_key[1])
        if row["source_revision"] != sources[source_key] or row["input_revision"] != inputs.get(variant_ids[row["variant_key"]]):
            continue
        snapshot = json.loads(row["snapshot_json"])
        if snapshot and pvs1.needs_review(dict(signature=row["signature"], snapshot=snapshot), row["signature"]):
            continue
        assessment = json.loads(row["result_json"])["assessment"]
        result.setdefault(row["variant_key"], []).append(dict(identity=identity, automatic=True,
            classification=assessment["classification"], points=assessment["total_points"], requires_review=assessment["requires_review"],
            applied_criteria=[{key: criterion[key] for key in ("code", "strength")} for criterion in assessment["criteria"]]))
    return result


def _worker_count(total, workers):
    if workers is None:
        try:
            cpus = len(os.sched_getaffinity(0))
        except (AttributeError, OSError):
            cpus = os.cpu_count() or 1
        workers = os.environ.get("HELPER_ACMG_WORKERS", min(4, cpus))
    workers = int(workers)
    if not 1 <= workers <= 16:
        raise ValueError("HELPER_ACMG_WORKERS must be between 1 and 16")
    return min(workers, max(1, total))


def prepare_run(database, record, evaluate, state, checkpoint, stopping, *, workers=None):
    """Bounded parallel evaluation, with durable checkpoints in allele order."""
    with store.connect(database) as db:
        total = db.execute("SELECT COUNT(*) FROM (SELECT DISTINCT a.sample_id,c.variant_id FROM calls c "
                           "JOIN analyses a ON a.id=c.analysis_id JOIN variants v ON v.id=c.variant_id WHERE "
                           + store.SEQUENCE_VARIANT_FILTER + ")").fetchone()[0]
    state.setdefault("attempted", 0)
    state.setdefault("errors", 0)
    workers = _worker_count(total, workers)
    state.update(status="running", total=total, workers=workers)
    checkpoint()
    with CacheWriter(record["run_dir"], coalesce_seconds=.005 if workers > 1 else 0) as writer:
        def work(row):
            if writer.error:
                raise CacheWriteError(str(writer.error)) from writer.error
            with use_writer(writer):
                return evaluate(dict(run_id=record["id"], sample_id=row["sample_id"], variant_id=row["variant_id"]))
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="acmg-variant") as pool:
            last_checkpoint = time.monotonic()
            while not stopping():
                sample, variant = state.get("after_sample", 0), state.get("after_variant", 0)
                with store.connect(database) as db:
                    rows = db.execute("SELECT DISTINCT a.sample_id,c.variant_id FROM calls c JOIN analyses a ON a.id=c.analysis_id "
                                      "JOIN variants v ON v.id=c.variant_id WHERE (a.sample_id>? OR (a.sample_id=? AND c.variant_id>?)) AND "
                                      + store.SEQUENCE_VARIANT_FILTER + " ORDER BY a.sample_id,c.variant_id LIMIT 50",
                                      (sample, sample, variant)).fetchall()
                if not rows:
                    state["status"] = "partial" if state["errors"] else "complete"
                    checkpoint()
                    return
                pending, finished = {}, {}
                submitted = committed = 0
                try:
                    while committed < len(rows):
                        if not stopping():
                            while submitted < len(rows) and len(pending) < workers * 2:
                                pending[pool.submit(work, rows[submitted])] = submitted
                                submitted += 1
                        if not pending:
                            break
                        done, _ = wait(pending, timeout=.2, return_when=FIRST_COMPLETED)
                        for future in done:
                            finished[pending.pop(future)] = future
                        while committed in finished:
                            row = rows[committed]
                            try:
                                result = finished.pop(committed).result()
                                state["errors"] += sum(bool(item.get("error")) for item in result.get("automatic", []))
                            except CacheWriteError:
                                raise
                            except Exception as exc:
                                state["errors"] += 1
                                state["last_error"] = str(exc)
                            state.update(attempted=state["attempted"] + 1,
                                         after_sample=row["sample_id"], after_variant=row["variant_id"])
                            committed += 1
                        if time.monotonic() - last_checkpoint >= 1:
                            checkpoint()
                            last_checkpoint = time.monotonic()
                        if stopping():
                            break
                finally:
                    for future in pending:
                        future.cancel()
                checkpoint()
    state["status"] = "interrupted"
    checkpoint()
