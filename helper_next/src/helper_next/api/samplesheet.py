import shutil
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import APIRouter
from pydantic import BaseModel

from helper_next.core.project import get_project_paths
from helper_next.core.samplesheet import (
    build_samplesheet,
    columns_for_step,
    default_organization_rows,
    load_samplesheet_text,
    resolve_file_paths,
    rows_from_files,
    suffixes_for_step,
)


router = APIRouter(prefix="/api/samplesheet", tags=["samplesheet"])


class FilePreviewRequest(BaseModel):
    step: str
    files: List[str]


class BuildRequest(BaseModel):
    step: str
    organization: str
    rows: List[Dict[str, str]]
    organization_rows: Optional[List[Dict[str, str]]] = None


class LoadRequest(BaseModel):
    content: str
    step: Optional[str] = None


class ResolveFilesRequest(BaseModel):
    files: List[str]
    roots: Optional[List[str]] = None


class PickerSelectionRequest(BaseModel):
    files: List[str]


PICKER_SELECTIONS = {}


@router.get("/steps")
def steps():
    return {
        "steps": [
            {"id": "prealignment", "label": "Pre-alignment", "columns": columns_for_step("prealignment")},
            {"id": "alignment", "label": "Alignment", "columns": columns_for_step("alignment")},
            {"id": "preprocessing", "label": "Pre-processing", "columns": columns_for_step("preprocessing")},
            {"id": "variantcalling", "label": "Variant calling", "columns": columns_for_step("variantcalling")},
            {"id": "postprocessing", "label": "Post-processing", "columns": columns_for_step("postprocessing")},
            {"id": "annotation", "label": "Annotation", "columns": columns_for_step("annotation")},
            {"id": "postannotation", "label": "Post-annotation", "columns": columns_for_step("postannotation")},
        ],
        "organizations": ["only cases", "case-control", "trio"],
    }


@router.post("/preview-files")
def preview_files(payload: FilePreviewRequest):
    resolved_files, resolve_warnings = resolve_file_paths(payload.files)
    rows, warnings = rows_from_files(payload.step, resolved_files)
    return {
        "columns": columns_for_step(payload.step),
        "rows": rows,
        "organization_rows": default_organization_rows(rows, "only cases"),
        "warnings": resolve_warnings + warnings,
    }


@router.post("/resolve-files")
def resolve_files(payload: ResolveFilesRequest):
    roots = [Path(root).expanduser() for root in payload.roots or []]
    resolved, warnings = resolve_file_paths(payload.files, roots)
    return {"files": resolved, "warnings": warnings}


@router.get("/browse-files")
def browse_files(step: str = "prealignment", path: Optional[str] = None):
    if path == "__other_locations__":
        return {
            "path": "__other_locations__",
            "parent": None,
            "roots": browse_roots(),
            "directories": [],
            "files": [],
            "locations": other_locations(),
            "warnings": [],
        }

    current = default_browse_path()
    explicit_path = bool(path)
    if path:
        requested = Path(path).expanduser()
        if requested.exists() and requested.is_dir():
            current = requested.resolve()

    suffixes = suffixes_for_step(step)
    directories, files, warnings = browse_directory(current, suffixes)

    if not explicit_path and not directories and not files and current != Path.home().resolve():
        current = Path.home().resolve()
        directories, files, warnings = browse_directory(current, suffixes)

    return {
        "path": str(current),
        "parent": str(current.parent) if current.parent != current else None,
        "roots": browse_roots(),
        "directories": directories,
        "files": files,
        "warnings": warnings,
    }


def browse_roots():
    roots = []

    def add_root(label, path):
        if path == "__other_locations__":
            roots.append({"label": label, "path": path})
            return
        resolved = Path(path).expanduser()
        if resolved.exists() and resolved.is_dir():
            item = {"label": label, "path": str(resolved.resolve())}
            if item not in roots:
                roots.append(item)

    home = Path.home()
    add_root("Home", home)
    add_root("Downloads", home / "Downloads")
    add_root("Documents", home / "Documents")
    add_root("Desktop", home / "Desktop")
    try:
        paths = get_project_paths()
        add_root("Helper", paths.root)
        add_root("Helper files", paths.files)
    except Exception:
        pass
    add_root("Other Locations", "__other_locations__")
    return roots


@router.post("/picker-selection/{picker_id}")
def save_picker_selection(picker_id: str, payload: PickerSelectionRequest):
    PICKER_SELECTIONS[picker_id] = payload.files
    return {"status": "ok", "count": len(payload.files)}


@router.get("/picker-selection/{picker_id}")
def get_picker_selection(picker_id: str):
    files = PICKER_SELECTIONS.pop(picker_id, [])
    return {"files": files}


def other_locations():
    computer = []
    networks = []
    seen = set()

    def add_location(section, name, path, device="", fstype=""):
        target = Path(path)
        if not target.exists() or not target.is_dir():
            return
        try:
            resolved = str(target.resolve())
        except OSError:
            return
        if resolved in seen:
            return
        seen.add(resolved)
        total, used, free = disk_usage_label(target)
        computer_or_network = networks if section == "Networks" else computer
        computer_or_network.append(
            {
                "section": section,
                "name": name,
                "path": resolved,
                "device": device,
                "detail": "{} / {} available".format(free, total) if total else "",
                "type": fstype,
            }
        )

    add_location("On this computer", "Computer", Path("/"), "/", "")

    for mount in mounted_locations():
        section = "Networks" if mount["network"] else "On this computer"
        add_location(section, mount["name"], mount["path"], mount["device"], mount["type"])

    return computer + networks


def mounted_locations():
    locations = []
    preferred_parents = [
        Path("/media") / Path.home().name,
        Path("/run/media") / Path.home().name,
        Path("/mnt"),
    ]

    mount_info = {}
    try:
        with open("/proc/mounts", "r") as mounts:
            for line in mounts:
                parts = line.split()
                if len(parts) < 3:
                    continue
                device, mount_point, fstype = parts[0], parts[1].replace("\\040", " "), parts[2]
                mount_info[mount_point] = {"device": device, "type": fstype}
    except OSError:
        pass

    for parent in preferred_parents:
        if parent.exists() and parent.is_dir():
            for child in sorted(parent.iterdir(), key=lambda item: item.name.lower()):
                info = mount_info.get(str(child), {})
                locations.append(
                    {
                        "name": child.name,
                        "path": child,
                        "device": info.get("device", ""),
                        "type": info.get("type", ""),
                        "network": is_network_mount(info.get("type", "")),
                    }
                )

    for mount_point, info in mount_info.items():
        device = info.get("device", "")
        fstype = info.get("type", "")
        if device.startswith("/dev/") or is_network_mount(fstype):
            path = Path(mount_point)
            locations.append(
                {
                    "name": path.name or mount_point,
                    "path": path,
                    "device": device,
                    "type": fstype,
                    "network": is_network_mount(fstype),
                }
            )

    return locations


def is_network_mount(fstype):
    return fstype in {"cifs", "nfs", "nfs4", "smb3", "sshfs", "fuse.sshfs", "davfs"}


def disk_usage_label(path):
    try:
        usage = shutil.disk_usage(str(path))
    except OSError:
        return "", "", ""
    return format_bytes(usage.total), format_bytes(usage.used), format_bytes(usage.free)


def format_bytes(value):
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    size = float(value)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return "{:.1f} {}".format(size, unit).replace(".0 ", " ")
        size /= 1024
    return "{} B".format(value)


def browse_directory(current, suffixes):
    directories = []
    files = []
    warnings = []

    try:
        entries = sorted(current.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower()))
    except OSError as error:
        entries = []
        warnings.append(str(error))

    for entry in entries:
        if entry.name.startswith("."):
            continue
        try:
            if entry.is_dir():
                directories.append({"name": entry.name, "path": str(entry.resolve())})
            elif entry.is_file() and entry.name.lower().endswith(suffixes):
                files.append({"name": entry.name, "path": str(entry.resolve()), "size": entry.stat().st_size})
        except OSError:
            continue

    return directories, files, warnings


def default_browse_path():
    try:
        paths = get_project_paths()
        if paths.files.exists() and any(paths.files.iterdir()):
            return paths.files.resolve()
        return Path.home().resolve()
    except Exception:
        return Path.home().resolve()


@router.post("/build")
def build(payload: BuildRequest):
    samplesheet = build_samplesheet(
        payload.step,
        payload.organization,
        payload.rows,
        payload.organization_rows,
    )
    return {"samplesheet": samplesheet}


@router.post("/load")
def load(payload: LoadRequest):
    return load_samplesheet_text(payload.content, payload.step)
