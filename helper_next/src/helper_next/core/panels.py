import json
import os
import re
import tempfile
from pathlib import Path


class PanelDesignError(ValueError):
    pass


PANEL_FIELDS = (
    "panel_name",
    "panel_technology",
    "gene_list",
    "transcripts_list",
    "target_list",
    "target_bed",
    "cnv_calls_model",
    "cnv_ploidy_model",
    "cnv_target_list",
    "cnv_exons_info",
)


def load_panel_config(configs_dir):
    path = Path(configs_dir) / "experiment_list.cfg"
    if not path.is_file():
        return {"list": []}
    try:
        with path.open(encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError) as exc:
        raise PanelDesignError("Could not read {}: {}".format(path.name, exc))
    if not isinstance(data, dict) or not isinstance(data.get("list"), list):
        raise PanelDesignError("{} must contain a JSON object with a list".format(path.name))
    return data


def save_panel_design(configs_dir, name, design, original_name=None):
    name = clean_value(name)
    if not name:
        raise PanelDesignError("Panel name is required")
    if not isinstance(design, dict):
        raise PanelDesignError("Panel design must be an object")

    data = load_panel_config(configs_dir)
    names = data["list"]
    source_name = clean_value(original_name) or name
    if source_name not in names and source_name in data:
        raise PanelDesignError("Panel design is not listed: {}".format(source_name))
    if source_name not in names and name in names:
        raise PanelDesignError("Panel design already exists: {}".format(name))
    if name != source_name and name in names:
        raise PanelDesignError("Panel design already exists: {}".format(name))

    existing = data.get(source_name, {})
    if not isinstance(existing, dict):
        existing = {}
    saved = dict(existing)
    for field in PANEL_FIELDS:
        if field in design or field == "panel_name":
            saved[field] = name if field == "panel_name" else clean_value(design[field])
        elif field not in saved:
            saved[field] = ""
    if not saved.get("target_bed"):
        raise PanelDesignError("target_bed is required")

    if source_name in names:
        index = names.index(source_name)
        if name != source_name:
            names[index] = name
            data.pop(source_name, None)
    else:
        names.append(name)
    data[name] = saved

    _write_panel_config(configs_dir, data)
    return {"name": name, "design": saved}


def delete_panel_design(configs_dir, name):
    name = clean_value(name)
    data = load_panel_config(configs_dir)
    names = data["list"]
    if name not in names:
        raise PanelDesignError("Panel design not found: {}".format(name))
    names.remove(name)
    data.pop(name, None)
    _write_panel_config(configs_dir, data)
    return {"deleted": name}


def _write_panel_config(configs_dir, data):
    path = Path(configs_dir) / "experiment_list.cfg"
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=str(path.parent),
            prefix=".experiment-list-", suffix=".tmp", delete=False
        ) as handle:
            temporary_path = Path(handle.name)
            json.dump(data, handle, indent=4, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(str(temporary_path), str(path))
    except OSError as exc:
        if temporary_path and temporary_path.exists():
            temporary_path.unlink()
        raise PanelDesignError("Could not save {}: {}".format(path.name, exc))


def load_panel_registry(configs_dir):
    data = load_panel_config(configs_dir)

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
