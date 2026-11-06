"""CACHE-06A: truthful local inventory and explicit metadata-only checks."""
import asyncio
import hashlib
import io
import json
import socket
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from helper_next.api.app import create_app
from helper_next.core import data_source_checks as checks, reference_validation
from helper_variants import clinvar_local as local, source_registry as registry, indexer
from test_clinvar_integration import install
from test_clinvar_local import inputs, submission
from test_biological_identity import reference_record


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("HELPER_TRANSCRIPT_CACHE", str(tmp_path / "transcripts"))
    monkeypatch.setenv("HELPER_REFERENCE_VALIDATION_DIR", str(tmp_path / "receipts"))
    monkeypatch.setenv("HELPER_DATA_SOURCES_STATE_DIR", str(tmp_path / "checks"))
    monkeypatch.setenv("HELPER_ENSEMBL_RELEASE", "116")
    configs = tmp_path / "configs"
    (configs / "tools_cfg").mkdir(parents=True)
    (configs / "tools_cfg/tools.cfg").write_text(json.dumps({
        "VEP v.116": {"version": "116", "path": "/configured/vep"},
    }))
    monkeypatch.setattr("helper_next.core.project.get_project_paths", lambda: SimpleNamespace(configs=configs))
    def forbidden(*args, **kwargs):
        pytest.fail("Inventory must not acquire data")
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(local, "urlopen", forbidden)
    monkeypatch.setattr(local, "download_sources", forbidden)
    monkeypatch.setattr(indexer, "sha256_file", forbidden)
    return configs


def inventory():
    return {source["source_id"]: source for source in registry.administrative_catalog()["sources"]}


def api(method, path, *, peer="127.0.0.1", base="http://127.0.0.1", headers=None):
    async def request():
        transport = httpx.ASGITransport(app=create_app(), client=(peer, 12345))
        async with httpx.AsyncClient(transport=transport, base_url=base) as client:
            return await asyncio.wait_for(client.request(method, path, headers=headers), timeout=5)
    return asyncio.run(request())


def completed():
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        with local.ClinVarLocal() as reader:
            snapshot = reader.release()["snapshot_id"]
        value = checks.check_status(snapshot_id=snapshot)
        if value["status"] != "running":
            return value
        time.sleep(.01)
    pytest.fail("Check did not finish")


def test_missing_inventory_does_not_create_caches_or_invent_versions(tmp_path):
    before = set(tmp_path.rglob("*"))
    rows = inventory()
    assert set(tmp_path.rglob("*")) == before
    assert len(rows) == 17
    vcep = rows["clingen_vcep_variants"]
    assert vcep["name"] == "ClinGen — VCEP Variant Classifications"
    assert vcep["status"] == "missing" and vcep["installed"] is False
    for field in ("version", "snapshot_id", "last_updated", "last_checked", "update_available"):
        assert vcep[field] is None
    assert vcep["update_supported"] is False
    assert "erepo.clinicalgenome.org" in vcep["source_url"]
    assert rows["gnomad"]["version"] is None
    assert rows["gnomad_frequency"]["version"] is None
    assert rows["gnomad_frequency"]["details"]["configured_datasets"]["GRCh38"]["release"] == "4.1.1"
    assert rows["gene_struct"]["version"] is None
    assert rows["gene_struct"]["details"]["configured_release"] == "116"
    assert rows["reference_grch38"]["status"] == "not_configured"
    assert rows["vep"]["installed"] is None
    assert rows["vep"]["details"]["configured_tools"][0]["version"] == "116"


def test_clinvar_current_backup_and_read_only_inventory(tmp_path, monkeypatch):
    target, first = install(tmp_path, monkeypatch)
    paths = inputs(tmp_path / "sources", submissions=[submission(scv="SCV000000900")])
    second = local.build_database(*paths, database=target)
    paths = list((target.parent / (target.name + ".snapshots")).glob("*.sqlite3"))
    before = [(p.read_bytes(), p.stat().st_mtime_ns) for p in paths]
    source = registry.administrative_catalog("clinvar")["sources"][0]
    assert source["snapshot_id"] == second["snapshot_id"]
    assert source["last_updated"] == second["imported_at"]
    assert source["version"] is None
    assert source["details"]["backup"]["snapshot_id"] == first["snapshot_id"]
    assert source["details"]["validation"] == "complete"
    assert source["details"]["size_bytes"] > 0
    assert source["details"]["manifest"]["sources"] == second["sources"]
    assert [(p.read_bytes(), p.stat().st_mtime_ns) for p in paths] == before
    assert len(paths) == 2


def test_installed_vcep_is_exposed_without_update_actions():
    from helper_variants import clingen_vcep_local as vcep
    fixture = Path(__file__).parent / "fixtures/clingen_vcep_local"
    installed = vcep.build_database(fixture / "erepo.tsv", summary=fixture / "summary.json")
    response = api("GET", "/api/data-sources/clingen_vcep_variants")
    assert response.status_code == 200
    source = response.json()
    assert source["installed"] and source["status"] == "installed"
    assert source["snapshot_id"] == installed["snapshot_id"]
    assert source["details"]["manifest"]["counts"]["assertions"] == 7
    assert source["update_supported"] is False
    assert "check" not in source and "can_update" not in source
    assert api("POST", "/api/data-sources/clingen_vcep_variants/check").status_code == 400


def test_corrupt_source_does_not_hide_other_sources(tmp_path, monkeypatch):
    target = tmp_path / "corrupt.sqlite3"
    target.write_bytes(b"not a sqlite database")
    monkeypatch.setenv("HELPER_CLINVAR_LOCAL_DB", str(target))
    monkeypatch.setenv("HELPER_GNOMAD_FREQUENCY_CACHE", str(target))
    rows = inventory()
    assert rows["clinvar"]["status"] == rows["gnomad_frequency"]["status"] == "error"
    assert rows["clinvar"]["error"]
    assert rows["clingen_vcep_variants"]["status"] == "missing"


def test_gene_sources_distinguish_optional_imports_and_have_no_release(monkeypatch):
    monkeypatch.setattr(registry.gene_phenotype, "cache_status", lambda: {
        "status": "ready", "row_count": 10, "g2p_row_count": 0,
        "g2p_source_url": "https://www.ebi.ac.uk/gene2phenotype/",
        "updated_at": "2026-10-29T12:00:00Z", "etag": "an-export-etag",
        "constraint_row_count": 0, "database": "/index.sqlite3",
    })
    rows = inventory()
    assert rows["gencc"]["installed"] is True
    assert rows["gencc"]["details"]["etag"] == "an-export-etag"
    assert rows["g2p"]["installed"] is True  # an imported empty export is valid
    assert rows["clingen_dosage"]["installed"] is False
    assert rows["gencc"]["version"] is rows["g2p"]["version"] is None
    assert rows["gencc"]["last_updated"] == "2026-10-29T12:00:00Z"


def test_reference_uses_receipt_without_hashing_and_invalidates_changed_fasta(tmp_path, monkeypatch):
    record = reference_record(tmp_path)
    # Permit the explicit test enrollment; consultation below must not hash.
    monkeypatch.setattr(indexer, "sha256_file", lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest())
    receipt = reference_validation.validate_reference("GRCh38", record, managed_immutable=True)
    config = tmp_path / "references.json"
    config.write_text(json.dumps({"GRCh38": {"version": "synthetic-reference-1", "fasta": record["run_config"]["reference_fasta"]}}))
    monkeypatch.setenv("HELPER_ACMG_REFERENCE_CONFIG", str(config))
    def forbidden(*args, **kwargs):
        pytest.fail("Consultation must not hash FASTA")
    monkeypatch.setattr(indexer, "sha256_file", forbidden)
    row = registry.administrative_catalog("reference_grch38")["sources"][0]
    assert row["details"]["validation"] == "verified"
    assert row["details"]["verified_sha256"] == receipt["digest"]["value"]
    assert row["details"]["verified_at"] == receipt["verified_at"]
    fasta = Path(record["run_config"]["reference_fasta"])
    fasta.write_bytes(fasta.read_bytes().replace(b"A", b"C", 1))
    changed = registry.administrative_catalog("reference_grch38")["sources"][0]
    assert changed["details"]["validation"] == "requires_validation"
    assert changed["details"]["verified_sha256"] is None


def test_transcript_metadata_not_configured_version(tmp_path):
    cache = tmp_path / "transcripts"
    cache.mkdir()
    (cache / "artifact.json").write_text(json.dumps({
        "key": {"schema": "helper-transcript-reference-1.0", "assembly": "GRCh38", "transcript": "ENST000001.2", "release": "115"},
        "acquired_at": "2026-10-28T12:00:00Z",
    }))
    row = registry.administrative_catalog("gene_struct")["sources"][0]
    assert row["version"] == "115"
    assert row["details"]["configured_release"] == "116"
    assert row["details"]["assemblies"] == ["GRCh38"]
    assert row["details"]["example_keys"][0]["transcript"] == "ENST000001.2"


def test_invalid_tools_configuration_is_an_error_without_breaking_catalog(isolated):
    (isolated / "tools_cfg/tools.cfg").write_text("[]")
    rows = inventory()
    assert rows["vep"]["status"] == "error"
    assert rows["reference_grch38"]["status"] == "error"
    assert rows["clingen_vcep_variants"]["status"] == "missing"


def test_local_ipv6_and_matching_origin_are_supported():
    response = api("GET", "/api/data-sources/clinvar/check", peer="::1",
                   base="http://[::1]:8770", headers={"Origin": "http://[::1]:8770"})
    assert response.status_code == 200


def test_check_receipt_is_readable_by_a_fresh_module_instance(tmp_path, monkeypatch):
    # Persistence is a receipt on disk, not a process-global task dictionary.
    import importlib.util
    target, release = install(tmp_path, monkeypatch)
    _, path, _ = checks._paths(target)
    path.parent.mkdir()
    checks._save(path, dict(status="complete", snapshot_id=release["snapshot_id"],
                            last_checked="2026-11-02T12:00:00Z", update_available=True, error=None))
    spec = importlib.util.spec_from_file_location("fresh_clinvar_check", checks.__file__)
    fresh = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fresh)
    result = fresh.check_status(target, release["snapshot_id"])
    assert result["update_available"] is True
    assert result["last_checked"] == "2026-11-02T12:00:00Z"


@pytest.mark.parametrize("peer,base,headers", [
    ("192.0.2.1", "http://127.0.0.1", {}),
    ("127.0.0.1", "http://attacker.test", {}),
    ("127.0.0.1", "http://localhost", {"Origin": "https://attacker.test"}),
    ("127.0.0.1", "http://localhost", {"Sec-Fetch-Site": "cross-site"}),
])
def test_admin_access_rejects_remote_and_cross_origin(peer, base, headers):
    for method, path in (("GET", ""), ("GET", "/clinvar"), ("POST", "/clinvar/check"), ("GET", "/clinvar/check"),
                         ("POST", "/clinvar/update"), ("POST", "/clinvar/postpone"), ("GET", "/clinvar/update/status")):
        response = api(method, "/api/data-sources" + path, peer=peer, base=base, headers=headers)
        assert response.status_code == 403
        assert "database" not in response.text


def test_api_unknown_unsupported_and_missing_are_explicit():
    assert api("GET", "/api/data-sources").status_code == 200
    assert api("GET", "/api/data-sources/unknown").status_code == 404
    assert api("POST", "/api/data-sources/clingen_vcep_variants/check").status_code == 400
    assert api("GET", "/api/data-sources/g2p/check").status_code == 400
    assert api("POST", "/api/data-sources/clinvar/check").status_code == 400
    response = api("GET", "/api/data-sources/clinvar/check")
    assert response.json()["status"] == "idle"
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("changed", [False, True])
def test_manual_check_is_nonblocking_deduplicated_and_checksum_only(tmp_path, monkeypatch, changed):
    target, release = install(tmp_path, monkeypatch)
    entered, unblock = threading.Event(), threading.Event()
    calls = []
    def remote(url, method="GET", timeout=120):
        calls.append((url, timeout))
        entered.set()
        assert unblock.wait(5)
        assert url.endswith(".md5")
        name = url.rsplit("/", 1)[-1][:-4]
        checksum = "0" * 32 if changed else release["sources"][name]["md5"]
        return io.BytesIO((checksum + "  " + name).encode())
    monkeypatch.setattr(local, "_request", remote)
    real_path = target.resolve()
    before = real_path.read_bytes()
    try:
        started = api("POST", "/api/data-sources/clinvar/check")
        assert started.status_code == 202
        assert entered.wait(2)
        assert started.json()["status"] == "running"
        assert api("GET", "/api/data-sources").status_code == 200
        duplicate = api("POST", "/api/data-sources/clinvar/check")
        assert duplicate.status_code == 202
        assert len(calls) == 1
    finally:
        unblock.set()
    result = completed()
    assert result["status"] == "complete"
    assert result["update_available"] is changed
    assert result["last_checked"]
    assert len(calls) == 2 and all(timeout == 15 for _, timeout in calls)
    assert real_path.read_bytes() == before
    row = api("GET", "/api/data-sources/clinvar").json()
    assert row["update_available"] is changed
    assert row["last_checked"] == result["last_checked"]
    # A changed CURRENT must not inherit an obsolete result.
    paths = inputs(tmp_path / "sources", submissions=[submission(scv="SCV000000900")])
    local.build_database(*paths, database=target)
    row = api("GET", "/api/data-sources/clinvar").json()
    assert row["update_available"] is None
    assert row["check"]["matches_current"] is False


def test_network_error_and_interrupted_receipt_are_visible(tmp_path, monkeypatch):
    install(tmp_path, monkeypatch)
    def timeout(*args, **kwargs):
        raise TimeoutError("NCBI timed out")
    monkeypatch.setattr(local, "_request", timeout)
    assert api("POST", "/api/data-sources/clinvar/check").status_code == 202
    result = completed()
    assert result["status"] == "error" and "timed out" in result["error"]
    assert result["last_checked"] and result["update_available"] is None
    _, path, _ = checks._paths()
    result.update(status="running")
    checks._save(path, result)
    assert "interrupted" in checks.check_status()["error"]
