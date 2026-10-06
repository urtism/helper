"""Create Helper archive entries from user-selected VCF files."""
import json
import os
import re
import shutil
from pathlib import Path
from uuid import uuid4

from helper_next.core import analysis_history


class ArchivedRunImportError(ValueError):
    pass


def imported_runs_root():
    configured = os.environ.get("HELPER_IMPORTED_RUNS_DIR")
    if configured:
        return Path(configured).expanduser()
    data_home = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share")))
    return data_home / "helper_next" / "imported_variant_runs"


def create_archived_run(files, name, reference_build, panel=""):
    sources = _validate_sources(files)
    name = str(name or "").strip()
    reference_build = str(reference_build or "").strip()
    if not name:
        raise ArchivedRunImportError("a run name is required")
    if not reference_build:
        raise ArchivedRunImportError("reference build is required")

    import_key = uuid4().hex
    run_dir = imported_runs_root() / import_key
    annotation_dir = run_dir / "results" / "ANNOTATION"
    try:
        annotation_dir.mkdir(parents=True, exist_ok=False)
        linked_sources = []
        for number, source in enumerate(sources, 1):
            suffix = ".annotated.vcf.gz" if source.name.lower().endswith(".vcf.gz") else ".annotated.vcf"
            stem = source.name[:-7] if source.name.lower().endswith(".vcf.gz") else source.stem
            safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._") or "variants"
            destination = annotation_dir / "{:04d}.{}{}".format(number, safe_stem, suffix)
            destination.symlink_to(source)
            linked_sources.append({
                "source_path": str(source), "linked_path": str(destination),
                "size_bytes": source.stat().st_size,
            })
        manifest = {
            "format": "helper-archived-variant-run-v1", "import_key": import_key,
            "name": name, "reference_build": reference_build,
            "panel": str(panel or "").strip(), "sources": linked_sources,
        }
        (run_dir / "variant-run.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        record = analysis_history.create({
            "run_id": name, "run_dir": str(run_dir), "status": "imported",
            "samples": [],
            "run_config": {"reference_version": reference_build},
            "request": {"gene_panel_design": str(panel or "").strip()},
            "imported_variant_run": True, "import_key": import_key,
            "variant_sources": linked_sources,
        })
    except Exception:
        if run_dir.is_dir():
            shutil.rmtree(str(run_dir))
        raise
    return record


def _validate_sources(files):
    sources = []
    seen = set()
    for value in files or []:
        source = Path(value).expanduser().resolve()
        lowered = source.name.lower()
        if not source.is_file():
            raise ArchivedRunImportError("VCF is not available: {}".format(source))
        if not lowered.endswith((".vcf", ".vcf.gz")):
            raise ArchivedRunImportError("only .vcf and .vcf.gz files are supported")
        if lowered.endswith((".g.vcf", ".g.vcf.gz")):
            raise ArchivedRunImportError("GVCF files must first be joint-genotyped into VCF")
        key = str(source)
        if key not in seen:
            sources.append(source)
            seen.add(key)
    if not sources:
        raise ArchivedRunImportError("select at least one VCF")
    return sources
