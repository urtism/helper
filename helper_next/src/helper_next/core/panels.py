import json
import re
from pathlib import Path


class PanelDesignError(ValueError):
    pass


def load_panel_registry(configs_dir):
    experiment_list = Path(configs_dir) / "experiment_list.cfg"
    if not experiment_list.is_file():
        return {"list": [], "designs": {}, "invalid": {}}

    with experiment_list.open() as handle:
        data = json.load(handle)

    designs = {}
    invalid = {}
    for source_name in data.get("list", []):
        if not isinstance(source_name, str):
            continue
        raw = data.get(source_name, {})
        if not isinstance(raw, dict):
            invalid[source_name] = ["design entry is not an object"]
            continue
        design = normalize_panel_design(source_name, raw)
        errors = validate_panel_design(design)
        if errors:
            invalid[source_name] = errors
        else:
            designs[source_name] = design

    return {"list": list(designs.keys()), "designs": designs, "invalid": invalid}


def get_panel_design(configs_dir, source_name):
    name = (source_name or "").strip()
    if not name:
        return None
    registry = load_panel_registry(configs_dir)
    if name in registry["designs"]:
        return registry["designs"][name]
    if name in registry["invalid"]:
        raise PanelDesignError("{}: {}".format(name, "; ".join(registry["invalid"][name])))
    raise PanelDesignError("Unknown panel design: {}".format(name))


def normalize_panel_design(source_name, raw):
    target_bed = clean_value(raw.get("target_bed"))
    design = {
        "schema_version": 1,
        "id": slugify(source_name),
        "source_name": source_name,
        "display_name": clean_value(raw.get("panel_name")) or source_name,
        "technology": normalize_technology(raw.get("panel_technology")),
        "assets": {
            "gene_list": clean_value(raw.get("gene_list")),
            "transcripts_list": clean_value(raw.get("transcripts_list")),
            "target_list": clean_value(raw.get("target_list")),
            "target_bed": target_bed,
        },
        "cnv": {
            "target_list": clean_value(raw.get("cnv_target_list")),
            "calls_model": clean_value(raw.get("cnv_calls_model")),
            "ploidy_model": clean_value(raw.get("cnv_ploidy_model")),
            "exons_info": clean_value(raw.get("cnv_exons_info")),
        },
        "validation": {
            "target_bed_present": bool(target_bed),
            "target_bed_exists": path_exists(target_bed),
        },
    }
    return design


def validate_panel_design(design):
    errors = []
    if not design.get("assets", {}).get("target_bed"):
        errors.append("target_bed is required")
    return errors


def clean_value(value):
    if value is None:
        return ""
    return str(value).strip()


def normalize_technology(value):
    text = clean_value(value)
    if not text:
        return "unknown"
    normalized = slugify(text)
    return normalized or "unknown"


def slugify(value):
    text = clean_value(value).lower()
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return text or "panel"


def path_exists(value):
    if not value:
        return False
    try:
        return Path(value).expanduser().exists()
    except OSError:
        return False
