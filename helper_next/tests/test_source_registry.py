from helper_variants import source_registry


def test_registry_separates_source_dates_from_local_snapshots(monkeypatch):
    monkeypatch.setattr(source_registry.gene_phenotype, "cache_status", lambda database=None: {
        "status": "ready", "stale": False, "database": "/not/read",
        "updated_at": "2026-10-06T12:00:00Z",
        "source_url": "https://example.test/gencc",
        "hpo_source_url": "https://example.test/hpo",
        "g2p_source_url": "https://example.test/g2p",
        "clingen_dosage_source_url": "https://example.test/dosage",
        "orphadata_source_url": "https://example.test/orpha",
    })
    monkeypatch.setattr(source_registry, "_gene_cache_metrics", lambda database: {
        "gencc": {"count": 30, "updated": "2026-10-04"},
        "hpo": {"count": 200, "updated": ""},
        "g2p": {"count": 40, "updated": "2026-10-02"},
        "clingen_dosage": {"count": 50, "updated": "2026-09-25"},
        "orphadata": {"count": 60, "updated": ""},
        "gnomad": {"count": 4, "updated": "2026-10-06T13:00:00Z"},
    })
    monkeypatch.setattr(source_registry.clinvar, "cache_status", lambda database=None: {
        "record_count": 7, "latest_record_update": "2026-09-27",
        "synchronized_at": "2026-10-06T13:40:00Z",
    })
    monkeypatch.setattr(source_registry.panelapp, "cache_status", lambda database=None: {
        "status": "ready", "stale": False, "panel_count": 433,
        "latest_panel_update": "2026-10-05T15:42:00Z",
        "synced_at": "2026-10-06T08:27:00Z",
    })
    monkeypatch.setattr(source_registry.liftover, "cache_status", lambda database=None: {
        "status": "ready", "record_count": 3,
        "synchronized_at": "2026-10-06T14:00:00Z",
    })

    result = source_registry.catalog()
    by_id = {item["id"]: item for item in result["sources"]}

    assert result["schema_version"] == "1"
    assert result["summary"] == {
        "total": 11, "on_demand": 4, "synchronized": 6, "bundled": 1,
    }
    assert by_id["gnomad"]["release"] == "v4.1.2"
    assert by_id["gnomad_frequency"]["release"] == "v2.1.1 (GRCh37); v4.1 (GRCh38)"
    assert by_id["gencc"]["data_updated_at"] == "2026-10-04"
    assert by_id["gencc"]["synchronized_at"] == "2026-10-06T12:00:00Z"
    assert by_id["panelapp"]["release"] == "Per-panel versions in catalogue snapshot"
    assert by_id["acmg_sf"]["release"].startswith("v3.3")
    assert by_id["clinvar"]["status"] == "on_demand"
    assert by_id["ncbi_variation"]["record_count"] == 3


def test_registry_marks_missing_snapshot_sources_unavailable(monkeypatch):
    monkeypatch.setattr(source_registry.gene_phenotype, "cache_status", lambda database=None: {
        "status": "missing", "database": "/not/read",
    })
    monkeypatch.setattr(source_registry, "_gene_cache_metrics", lambda database: {
        key: {"count": 0, "updated": ""}
        for key in ("gencc", "hpo", "g2p", "clingen_dosage", "orphadata", "gnomad")
    })
    monkeypatch.setattr(source_registry.clinvar, "cache_status", lambda database=None: {})
    monkeypatch.setattr(source_registry.panelapp, "cache_status", lambda database=None: {
        "status": "missing",
    })
    monkeypatch.setattr(source_registry.liftover, "cache_status", lambda database=None: {
        "status": "missing",
    })

    by_id = {item["id"]: item for item in source_registry.catalog()["sources"]}

    assert by_id["gencc"]["status"] == "unavailable"
    assert by_id["hpo"]["status"] == "unavailable"
    assert by_id["panelapp"]["status"] == "unavailable"
