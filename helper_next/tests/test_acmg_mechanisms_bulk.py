"""Task 27A.1: local enumeration, durable progress and resolver-only publication."""
import copy
import io
import json
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from helper_next.acmg_mechanisms_bulk import main
from helper_next.core import acmg_mechanism_normalizer as norm
from helper_next.core.acmg_mechanism_store import MechanismStore
from helper_next.core.acmg_mechanisms import MechanismEvidenceCache
from helper_next.core.acmg_mechanisms_bulk import BulkPopulation, build_inventory
from helper_next.core.acmg_sources import SourceManager
from helper_variants import gene_phenotype
from test_gene_phenotype import HEADER


@pytest.fixture
def population(tmp_path, monkeypatch):
    source_db = tmp_path / "source.sqlite"
    cache_db = tmp_path / "mechanisms.sqlite"
    gencc = HEADER + (
        "SGC-1,1,HGNC:1,GENE_X,OMIM:1,One,MONDO:1,One,Strong,,monoallelic,Synthetic,2026-01-01,https://example.test/a,PMID:1,,2026-01-02\n"
        "SGC-2,2,HGNC:1,GENE_X,MONDO:1,One,,,Strong,,Autosomal dominant,Synthetic,2026-01-01,https://example.test/b,PMID:2,,2026-01-02\n"
        "SGC-3,1,HGNC:3,GENE_Z,MONDO:3,Three,,,Strong,,Autosomal dominant,Synthetic,2026-01-01,https://example.test/c,PMID:3,,2026-01-02\n")
    g2p = ("g2p id,gene symbol,hgnc id,disease name,disease MONDO,disease mim,allelic requirement,confidence,molecular mechanism\n"
           "G2P-1,GENE_X,HGNC:1,One,MONDO:1,1,monoallelic,strong,loss of function\n"
           "G2P-2,GENE_X,HGNC:1,Two,MONDO:2,2,monoallelic,strong,gain of function\n"
           "G2P-3,GENE_Y,HGNC:2,Two,MONDO:2,2,biallelic,strong,loss of function\n")
    dosage = ("#Gene Symbol\tGene ID\tHaploinsufficiency Score\tTriplosensitivity Score\n"
              "GENE_X\t111\t3\t0\n")
    gene_phenotype.build_cache(io.StringIO(gencc), source_db, g2p_stream=io.StringIO(g2p), dosage_stream=io.StringIO(dosage))
    with sqlite3.connect(source_db) as db:
        stamp = dict(db.execute("SELECT key,value FROM metadata"))["updated_at"]
        db.execute("INSERT INTO gnomad_constraints(gene_symbol,gene_id,transcript_id,available,loeuf,updated_at,source_url) VALUES(?,?,?,?,?,?,?)",
                   ("GENE_X", "ENSG000001", "ENST000001.1", 1, 0.2, stamp, "https://example.test/constraint"))
    monkeypatch.setenv("HELPER_MECHANISM_DB", str(cache_db))
    monkeypatch.setenv("HELPER_GENE_PHENOTYPE_DB", str(source_db))
    monkeypatch.setenv("HELPER_MECHANISM_FETCH", "0")
    from helper_next.core.acmg_ontology import OntologyMappingRegistry
    from test_acmg_ontology import load_reference
    registry = OntologyMappingRegistry(MechanismStore(tmp_path / "reference.sqlite"))
    load_reference(registry, tmp_path, [("MONDO:1", "skos:exactMatch", "OMIM:1"),
                                        ("MONDO:2", "skos:exactMatch", "OMIM:2")])
    monkeypatch.setattr(SourceManager, "ontology_registry", lambda self, store=None: registry)
    cache = MechanismEvidenceCache(SourceManager(gene_database=source_db, mechanism_fetch=False), cache_db)
    return BulkPopulation(cache), source_db, cache_db


def test_dry_run_normalizes_deduplicates_attested_aliases_and_preserves_inheritance(population):
    runner, source_db, cache_db = population
    original = source_db.read_bytes()
    inventory = build_inventory(runner.cache.sources)
    report = runner.run(dry_run=True, offline=True)
    assert report["source_records"] == {"g2p": 3, "gencc": 3}
    assert report["source_associations"] == {"g2p": 3, "gencc": 3}
    assert report["unique_associations"] == report["to_process"] == 5
    assert report["matrices_saved"] == report["snapshots_created"] == 0
    one = [a for a in inventory["associations"] if a["gene"] == "HGNC:1" and a["disease"] == "MONDO:1"]
    assert {a["allelic_requirement"] for a in one} == {"AUTOSOMAL_DOMINANT", "MONOALLELIC"}
    assert not cache_db.exists() and source_db.read_bytes() == original


def test_limited_population_resume_and_idempotent_second_run(population):
    runner, _, _ = population
    limited = runner.run(limit=2, offline=True)
    assert limited["status"] == "LIMITED"
    assert limited["processed"] == limited["matrices_saved"] == limited["snapshots_created"] == 2
    assert limited["remaining"] == 3 and not limited["local_population_complete"]
    completed = runner.run(resume=True, offline=True)
    assert completed["run_id"] == limited["run_id"] and completed["status"] == "COMPLETED"
    assert completed["processed"] == completed["matrices_saved"] == completed["snapshots_created"] == 5
    assert completed["matrices_with_direct_assertion"] == 3
    assert completed["matrices_context_only"] == 2
    assert completed["local_population_complete"]
    repeated = runner.run(offline=True)
    assert repeated["snapshots_created"] == repeated["matrices_created"] == repeated["matrices_updated"] == 0
    assert repeated["matrices_saved"] == repeated["processed"] == 5
    assert runner.store.statistics()["snapshots"] == 5


def test_interruption_after_snapshot_commit_is_replayed_without_duplicate_snapshot(population, monkeypatch):
    runner, _, _ = population
    original = runner.store.finish_bulk_item
    once = [True]

    def interrupted(*args, **kwargs):
        if once[0]:
            once[0] = False
            raise KeyboardInterrupt()
        return original(*args, **kwargs)

    monkeypatch.setattr(runner.store, "finish_bulk_item", interrupted)
    with pytest.raises(KeyboardInterrupt):
        runner.run(offline=True)
    status = runner.report()
    assert status["status"] == "INTERRUPTED" and status["snapshots_created"] == 1
    assert runner.store.statistics()["snapshots"] == 1
    result = runner.run(resume=True, offline=True)
    assert result["processed"] == result["snapshots_created"] == 5
    assert runner.store.statistics()["snapshots"] == 5


def test_incremental_refresh_only_changed_association_same_gene(population):
    runner, source_db, _ = population
    runner.run(offline=True)
    before = {i["association_key"]: i["snapshot_id"] for i in runner.store.bulk_items(runner.store.bulk_run()["run_id"])}
    with sqlite3.connect(source_db) as db:
        db.execute("UPDATE g2p_records SET mechanism='dominant negative' WHERE g2p_id='G2P-2'")
    dry = runner.run(dry_run=True, refresh_stale=True, offline=True)
    assert dry["to_process"] == 1
    result = runner.run(refresh_stale=True, offline=True)
    assert result["processed"] == result["matrices_updated"] == result["snapshots_created"] == 1
    assert result["matrices_created"] == 0
    changed = runner.store.bulk_items(result["run_id"])[0]
    assert runner.store.snapshot(changed["snapshot_id"]).candidate_mechanisms == ["DOMINANT_NEGATIVE"]
    assert runner.store.snapshot(before[changed["association_key"]]).candidate_mechanisms == ["GAIN_OF_FUNCTION"]
    for key, snapshot in before.items():
        if key != changed["association_key"]:
            assert runner.store.peek(key).snapshot_id == snapshot


def test_same_gene_multiple_changed_matrices_rebuild_from_current_source_state(population):
    runner, source_db, _ = population
    runner.run(offline=True)
    with sqlite3.connect(source_db) as db:
        db.execute("UPDATE g2p_records SET mechanism='dominant negative' WHERE gene_curie='HGNC:1'")
    result = runner.run(refresh_stale=True, offline=True)
    # MONDO:1 has two inheritance scopes, MONDO:2 has one.
    assert result["processed"] == 3
    direct = [runner.store.snapshot(i["snapshot_id"]) for i in runner.store.bulk_items(result["run_id"])]
    assert all(r.candidate_mechanisms == ["DOMINANT_NEGATIVE"] for r in direct if r.identity.allelic_requirement == "MONOALLELIC")


def test_refresh_stale_excludes_missing_and_fresh_matrices(population):
    runner, _, _ = population
    assert runner.run(dry_run=True, refresh_stale=True, offline=True)["to_process"] == 0
    runner.run(limit=1, offline=True)
    assert runner.run(dry_run=True, refresh_stale=True, offline=True)["to_process"] == 0
    runner.cache.clock = lambda: 10**12
    assert runner.run(dry_run=True, refresh_stale=True, offline=True)["to_process"] == 1


def test_offline_overrides_remote_environment_and_keeps_context_evidence(population, monkeypatch):
    runner, _, _ = population
    runner.cache.sources.mechanism_fetch = None
    monkeypatch.setenv("HELPER_MECHANISM_FETCH", "1")
    monkeypatch.setattr(gene_phenotype, "refresh_gnomad_constraint", lambda *a, **k: pytest.fail("No remote fetch allowed"))
    result = runner.run(offline=True)
    assert runner.cache.sources.mechanism_fetch is None  # No shared configuration mutation.
    snapshots = [runner.store.snapshot(i["snapshot_id"]) for i in runner.store.bulk_items(result["run_id"])]
    with_context = next(r for r in snapshots if r.identity.gene_id == "HGNC:1" and r.direct_evidence)
    assert {e.source for e in with_context.contextual_evidence} >= {"clingen_dosage", "gnomad"}
    assert all(r.review_status == "NOT_REVIEWED" for r in snapshots)


@pytest.mark.parametrize("problem", ["missing", "not_synced", "wrong_schema", "empty", "bad_date"])
def test_incomplete_indexes_never_claim_exhaustive_population(population, tmp_path, problem):
    runner, source_db, cache_db = population
    if problem == "missing":
        runner.cache.sources.gene_database = tmp_path / "absent.sqlite"
    else:
        with sqlite3.connect(source_db) as db:
            if problem == "not_synced":
                db.execute("UPDATE metadata SET value='' WHERE key='g2p_source_url'")
            elif problem == "wrong_schema":
                db.execute("UPDATE metadata SET value='0' WHERE key='schema_version'")
            elif problem == "empty":
                db.execute("DELETE FROM assertions")
            else:
                db.execute("UPDATE metadata SET value='not-a-date' WHERE key='updated_at'")
    report = runner.run(offline=True)
    assert report["status"] == "PREFLIGHT_FAILED" and report["source_problems"]
    assert report["processed"] == 0 and not cache_db.exists()


def test_stale_index_is_explicit_and_never_relabelled_fresh(population):
    runner, source_db, _ = population
    with sqlite3.connect(source_db) as db:
        db.execute("UPDATE metadata SET value='2000-01-01T00:00:00Z' WHERE key='updated_at'")
    report = runner.run(limit=1, offline=True)
    assert report["index_stale"] and report["source_status"]["g2p"]["status"] == "STALE"
    item = runner.store.bulk_items(report["run_id"])[0]
    assert any(s.stale for s in runner.store.snapshot(item["snapshot_id"]).source_status if s.source == "g2p")


def test_malformed_records_report_exclusions_and_same_names_do_not_merge(population):
    runner, source_db, _ = population
    with sqlite3.connect(source_db) as db:
        db.execute("UPDATE g2p_records SET disease_name='One' WHERE g2p_id='G2P-2'")
        db.execute("UPDATE g2p_records SET disease_curie='',disease_mim='' WHERE g2p_id='G2P-3'")
    report = runner.run(offline=True)
    assert report["invalid_records"] == 1 and report["invalid_record_reasons"] == {"MISSING_DISEASE_ID": 1}
    assert not report["local_population_complete"]
    items = runner.store.bulk_items(report["run_id"])
    assert {i["association"]["disease"] for i in items if i["association"]["gene"] == "HGNC:1"} == {"MONDO:1", "MONDO:2"}


def test_ambiguous_disease_mapping_never_collapses_primary_diseases(population):
    runner, source_db, _ = population
    from test_acmg_ontology import load_reference
    load_reference(runner.cache.registry, source_db.parent,
                   [("MONDO:1", "skos:exactMatch", "OMIM:1"), ("MONDO:2", "skos:exactMatch", "OMIM:1")], "synthetic-ambiguous")
    with sqlite3.connect(source_db) as db:
        db.execute("UPDATE g2p_records SET disease_mim='OMIM:1' WHERE gene_curie='HGNC:1'")
    inventory = build_inventory(runner.cache.sources)
    assert inventory["report"]["ambiguous_mapping_associations"] > 0
    assert {a["disease"] for a in inventory["associations"] if a["gene"] == "HGNC:1"} >= {"MONDO:1", "MONDO:2"}


def test_source_error_does_not_mark_association_completed_and_resume_retries(population, monkeypatch):
    runner, _, _ = population
    original = runner.cache.sources.mechanism_records

    def unavailable(*args, **kwargs):
        data = original(*args, **kwargs)
        if "g2p" in data:
            data["g2p"].update(status="UNREACHABLE", records=[])
        return data

    monkeypatch.setattr(runner.cache.sources, "mechanism_records", unavailable)
    failed = runner.run(limit=1, offline=True)
    assert failed["errors"] == 1 and failed["error_examples"][0]["code"] == "SOURCE_REFRESH_FAILED"
    monkeypatch.setattr(runner.cache.sources, "mechanism_records", original)
    assert runner.run(resume=True, offline=True)["errors"] == 0


def test_resume_rejects_changed_inventory_and_allows_updated_new_plan(population):
    runner, source_db, _ = population
    runner.run(limit=1, offline=True)
    with sqlite3.connect(source_db) as db:
        db.execute("UPDATE g2p_records SET mechanism='dominant negative' WHERE g2p_id='G2P-1'")
    with pytest.raises(ValueError, match="inventory changed"):
        runner.run(resume=True, offline=True)
    assert runner.run(offline=True)["status"] == "COMPLETED"


def test_per_item_errors_are_persistent_and_retryable(population, monkeypatch):
    runner, _, _ = population
    original = runner.cache.resolve_gene_disease_mechanism
    once = [True]

    def failed(*args, **kwargs):
        if once[0]:
            once[0] = False
            raise ValueError("synthetic failure")
        return original(*args, **kwargs)

    monkeypatch.setattr(runner.cache, "resolve_gene_disease_mechanism", failed)
    result = runner.run(offline=True)
    assert result["errors"] == 1 and result["status"] == "COMPLETED_WITH_ERRORS"
    resumed = runner.run(resume=True, offline=True)
    assert resumed["errors"] == 0 and resumed["successful"] == 5 and resumed["snapshots_created"] == 5


def test_concurrent_bulk_run_is_rejected_before_second_job_is_created(population, monkeypatch):
    runner, _, _ = population
    entered, release = threading.Event(), threading.Event()
    original = runner.cache.resolve_gene_disease_mechanism

    def blocked(*args, **kwargs):
        entered.set()
        assert release.wait(10)
        return original(*args, **kwargs)

    monkeypatch.setattr(runner.cache, "resolve_gene_disease_mechanism", blocked)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(runner.run, offline=True, limit=1)
        assert entered.wait(10)
        try:
            with pytest.raises(TimeoutError):
                runner.run(offline=True, limit=1)
        finally:
            release.set()
        assert future.result(timeout=10)["processed"] == 1
    with runner.store.readonly() as db:
        assert db.execute("SELECT COUNT(*) FROM mechanism_bulk_runs").fetchone()[0] == 1


def test_status_and_dry_run_do_not_write_or_migrate_existing_v1_cache(population):
    runner, _, cache_db = population
    inventory = build_inventory(runner.cache.sources)
    assoc = inventory["associations"][0]
    result = runner.cache.resolve_gene_disease_mechanism(assoc["gene"], assoc["disease"], assoc["resolver_requirement"])
    with runner.store.connect() as db:
        for table in ("mechanism_bulk_publications", "mechanism_bulk_items", "mechanism_bulk_runs"):
            db.execute("DROP TABLE " + table)
        db.execute("PRAGMA user_version=1")
    before = cache_db.read_bytes()
    assert runner.report()["status"] == "NOT_STARTED"
    runner.run(dry_run=True, offline=True)
    assert before == cache_db.read_bytes()
    runner.run(limit=1, offline=True)
    with runner.store.readonly() as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 3
    assert runner.store.snapshot(result.snapshot_id).snapshot_id == result.snapshot_id


def test_cli_dry_run_status_limit_resume_and_report_file(population, tmp_path, capsys):
    _, _, cache_db = population
    output = tmp_path / "report.json"
    assert main(["--dry-run", "--offline", "--limit", "2", "--json", "--report", str(output)]) == 0
    assert json.loads(capsys.readouterr().out)["to_process"] == 2 and not cache_db.exists()
    assert main(["--status", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "NOT_STARTED"
    assert main(["--populate", "--offline", "--limit", "2", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "LIMITED"
    assert main(["--resume", "--offline", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["successful"] == 5
    with pytest.raises(SystemExit):
        main(["--populate", "--limit", "0"])


def test_cli_missing_source_is_explicit_and_report_cannot_overwrite_index(population, tmp_path, capsys):
    _, source_db, cache_db = population
    assert main(["--dry-run", "--source-db", str(tmp_path / "absent"), "--json"]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "PREFLIGHT_FAILED"
    before = source_db.read_bytes()
    with pytest.raises(SystemExit):
        main(["--dry-run", "--report", str(source_db)])
    assert source_db.read_bytes() == before and not cache_db.exists()
