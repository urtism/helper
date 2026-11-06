import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest

from helper_next.api.app import create_app
from helper_next.core.panels import (
    PanelDesignError,
    delete_panel_design,
    load_panel_config,
    save_panel_design,
)


def test_save_panel_design_updates_existing_entry_and_preserves_legacy_fields(tmp_path):
    configs = tmp_path / "configs"
    configs.mkdir()
    path = configs / "experiment_list.cfg"
    path.write_text(
        json.dumps(
            {
                "list": ["Cardio"],
                "Cardio": {
                    "panel_name": "Cardio",
                    "target_bed": "/targets/cardio.bed",
                    "cnv_exons_info": "/targets/exons.txt",
                    "custom_legacy_field": "keep me",
                },
                "unlisted": {"retained": True},
            }
        ),
        encoding="utf-8",
    )

    save_panel_design(
        configs,
        "Cardio",
        {"panel_name": "Cardio", "target_bed": "/targets/cardio-v2.bed"},
        "Cardio",
    )

    saved = load_panel_config(configs)
    assert saved["list"] == ["Cardio"]
    assert saved["Cardio"]["target_bed"] == "/targets/cardio-v2.bed"
    assert saved["Cardio"]["cnv_exons_info"] == "/targets/exons.txt"
    assert saved["Cardio"]["custom_legacy_field"] == "keep me"
    assert saved["unlisted"] == {"retained": True}


def test_save_panel_design_creates_and_renames_design(tmp_path):
    configs = tmp_path / "configs"
    configs.mkdir()
    save_panel_design(
        configs,
        "Cardio v2",
        {"panel_technology": "Capture Enrichment", "target_bed": "/targets/cardio.bed"},
    )

    saved = load_panel_config(configs)
    assert saved["list"] == ["Cardio v2"]
    assert saved["Cardio v2"]["panel_name"] == "Cardio v2"
    assert saved["Cardio v2"]["cnv_calls_model"] == ""

    save_panel_design(
        configs,
        "Cardio v3",
        {"target_bed": "/targets/cardio-v3.bed"},
        "Cardio v2",
    )
    saved = load_panel_config(configs)
    assert saved["list"] == ["Cardio v3"]
    assert "Cardio v2" not in saved
    assert saved["Cardio v3"]["panel_technology"] == "Capture Enrichment"


def test_save_panel_design_rejects_missing_target_bed_without_writing(tmp_path):
    configs = tmp_path / "configs"
    configs.mkdir()
    with pytest.raises(PanelDesignError, match="target_bed is required"):
        save_panel_design(configs, "Panel", {"panel_name": "Panel"})
    assert not (configs / "experiment_list.cfg").exists()


def test_delete_panel_design_removes_name_and_entry(tmp_path):
    configs = tmp_path / "configs"
    configs.mkdir()
    path = configs / "experiment_list.cfg"
    path.write_text(json.dumps({"list": ["Panel"], "Panel": {"target_bed": "/x.bed"}}), encoding="utf-8")

    assert delete_panel_design(configs, "Panel") == {"deleted": "Panel"}
    assert load_panel_config(configs) == {"list": []}


def test_delete_panel_design_rejects_unknown_name(tmp_path):
    configs = tmp_path / "configs"
    configs.mkdir()
    with pytest.raises(PanelDesignError, match="not found"):
        delete_panel_design(configs, "Missing")


def test_panel_api_supports_list_save_and_delete(tmp_path, monkeypatch):
    configs = tmp_path / "configs"
    configs.mkdir()
    monkeypatch.setattr(
        "helper_next.api.panels.get_project_paths",
        lambda: SimpleNamespace(configs=configs),
    )
    app = create_app()

    async def exercise_api():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            initial = await client.get("/api/panels")
            created = await client.put(
                "/api/panels",
                json={
                    "name": "Panel A",
                    "design": {
                        "panel_name": "Panel A",
                        "target_bed": "/targets/a.bed",
                        "cnv_calls_model": "/models/calls",
                        "cnv_ploidy_model": "/models/ploidy",
                    },
                },
            )
            listed = await client.get("/api/panels")
            deleted = await client.delete("/api/panels/Panel%20A")
            missing = await client.delete("/api/panels/Panel%20A")
        return initial, created, listed, deleted, missing

    initial, created, listed, deleted, missing = asyncio.run(exercise_api())
    assert initial.json() == {"panels": []}
    assert created.status_code == 200
    assert listed.json()["panels"][0]["design"]["cnv_ploidy_model"] == "/models/ploidy"
    assert deleted.json() == {"deleted": "Panel A"}
    assert missing.status_code == 404
