import pytest

from helper_variants import panelapp
from helper_variants import secondary_findings


def test_search_panels_filters_locally_and_prioritizes_exact_id(monkeypatch):
    monkeypatch.setattr(panelapp, "_panel_catalog", lambda: [
        {"id": 12, "name": "Hereditary ataxia", "version": "3.2", "disease_group": "Neurology",
         "relevant_disorders": ["R54"], "stats": {"number_of_genes": 42}, "types": []},
        {"id": 54, "name": "Other panel", "version": "1.0", "disease_group": "",
         "relevant_disorders": ["Hereditary ataxia"], "stats": {"number_of_genes": 2}, "types": []},
    ])

    by_name = panelapp.search_panels("ataxia")
    by_id = panelapp.search_panels("12")

    assert [item["id"] for item in by_name["panels"]] == [12, 54]
    assert [item["id"] for item in by_id["panels"]] == [12]
    assert [item["id"] for item in panelapp.search_panels("5")["panels"]] == [12, 54]
    with pytest.raises(panelapp.PanelAppError, match="at least 2"):
        panelapp.search_panels("a")


def test_panel_detail_returns_only_gene_entities_grouped_by_confidence(monkeypatch):
    monkeypatch.setattr(panelapp, "_get_json", lambda url: {
        "id": 101, "name": "Example", "version": "2.4", "version_created": "2026-01-02T00:00:00Z",
        "stats": {"number_of_genes": 3}, "types": [{"name": "GMS signed-off"}],
        "genes": [
            {"entity_type": "gene", "gene_data": {"hgnc_symbol": "GENE3"},
             "confidence_level": "3", "mode_of_inheritance": "BIALLELIC"},
            {"entity_type": "gene", "gene_data": {"gene_symbol": "GENE2"},
             "confidence_level": "2"},
            {"entity_type": "gene", "entity_name": "GENE1", "gene_data": {},
             "confidence_level": "1"},
            {"entity_type": "str", "entity_name": "STR1", "confidence_level": "3"},
        ],
    })

    result = panelapp.panel_detail(101)

    assert result["genes"] == {"green": ["GENE3"], "amber": ["GENE2"], "red": ["GENE1"]}
    assert result["gene_counts"] == {"green": 1, "amber": 1, "red": 1}
    assert result["gene_records"][0]["mode_of_inheritance"] == "BIALLELIC"
    assert result["source_url"].endswith("/panels/101/")


def test_acmg_secondary_findings_snapshots_are_versioned_and_cumulative():
    panels = secondary_findings.catalog()
    counts = {panel["version"]: panel["gene_count"] for panel in panels}

    assert counts == {"3.3": 84, "3.2": 81, "3.1": 78, "3.0": 73}
    assert secondary_findings.detail("sf-v3.3")["current"] is True
    assert {"ABCD1", "CYP27A1", "PLN"}.issubset(
        secondary_findings.detail("sf-v3.3")["genes"]["all"]
    )


def test_panel_catalog_is_persisted_and_reused_without_network(tmp_path, monkeypatch):
    cache = tmp_path / "panelapp.json"
    monkeypatch.setenv("HELPER_PANELAPP_CACHE", str(cache))
    monkeypatch.setattr(panelapp, "_cache", {"expires": 0.0, "panels": []})
    monkeypatch.setattr(panelapp, "_fetch_catalog", lambda: [{
        "id": 1, "name": "Cached panel", "version": "1.0", "stats": {"number_of_genes": 2},
    }])

    first = panelapp.list_panels()
    panelapp._cache = {"expires": 0.0, "panels": []}
    monkeypatch.setattr(panelapp, "_fetch_catalog", lambda: pytest.fail("network should not be called"))
    second = panelapp.list_panels()

    assert cache.is_file()
    assert first["panels"] == second["panels"]


def test_panel_detail_is_reused_from_persistent_cache(tmp_path, monkeypatch):
    cache = tmp_path / "catalog.json"
    monkeypatch.setenv("HELPER_PANELAPP_CACHE", str(cache))
    calls = []

    def fetch(url):
        calls.append(url)
        return {
            "id": 42, "name": "TAAD", "version": "4.0",
            "stats": {"number_of_genes": 1},
            "genes": [{
                "entity_type": "gene", "entity_name": "FBN1",
                "confidence_level": "3",
            }],
        }

    monkeypatch.setattr(panelapp, "_get_json", fetch)
    first = panelapp.panel_detail(42)
    monkeypatch.setattr(panelapp, "_get_json", lambda url: pytest.fail("network should not be called"))
    second = panelapp.panel_detail(42)

    assert len(calls) == 1
    assert first == second
    assert second["genes"]["green"] == ["FBN1"]
