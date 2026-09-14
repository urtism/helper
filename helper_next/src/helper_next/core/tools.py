import copy
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


DEFAULT_TOOLS_FILE = "tools_cfg/tools.cfg"
TOOLS_SUFFIXES = (".cfg", ".json")
RESOURCE_TYPES = ("tool", "database", "reference")
DEFAULT_TOOL_CATEGORIES = (
    "trim_adapters", "fastq_QC", "fastq_alignment", "sam_to_bam", "sortSam", "indexBam", "bam_QC",
    "add_readgroups", "mark_pcr_dup", "indel_realignment", "BQ_recalibration", "variantcalling",
    "cnvcalling", "svcalling", "methylation", "vcf_norm", "vcf_filter", "vcf_to_tsv", "variant_ann",
    "ann_vcf_to_tsv",
)
NAME_PATTERN = re.compile(r"^[^/\\\x00]+$")


class ToolsError(ValueError):
    pass


def tools_path(configs_dir, filename=DEFAULT_TOOLS_FILE):
    root = Path(configs_dir).resolve()
    relative = str(filename or DEFAULT_TOOLS_FILE).strip()
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        raise ToolsError("Tools file must be inside the configs directory")
    if candidate.suffix.lower() not in TOOLS_SUFFIXES or "tool" not in candidate.name.lower():
        raise ToolsError("Tools file must be a .cfg or .json file whose name contains 'tool'")
    return candidate


def load_tools(configs_dir, pipelines_dir, filename=DEFAULT_TOOLS_FILE):
    path = tools_path(configs_dir, filename)
    if not path.is_file():
        raise ToolsError("Tools configuration not found: {}".format(filename))
    try:
        raw = path.read_bytes()
        config = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise ToolsError("Could not read {}: {}".format(filename, exc))
    if not isinstance(config, dict):
        raise ToolsError("Tools configuration must contain a JSON object")
    normalized = normalize_tools(config)
    return {
        "filename": str(path.relative_to(Path(configs_dir).resolve())),
        "revision": hashlib.sha256(raw).hexdigest(),
        "config": normalized,
        "categories": tool_categories(normalized),
        "resources": resource_catalog(normalized, pipelines_dir),
        "audit": audit_tools(normalized, pipelines_dir),
    }


def normalize_tools(config):
    result = copy.deepcopy(config) if isinstance(config, dict) else {}
    tools = result.get("tools")
    if not isinstance(tools, dict):
        tools = {}
        result["tools"] = tools
    databases = result.get("databases")
    if not isinstance(databases, dict):
        databases = {}
        result["databases"] = databases

    legacy_tools = result.pop("tools_list", [])
    legacy_databases = result.pop("databases_list", [])
    tools["list"] = clean_names(tools.get("list", legacy_tools))
    databases["list"] = clean_names(databases.get("list", legacy_databases))
    result["refGenomes_list"] = clean_names(result.get("refGenomes_list", []))

    for key, values in list(tools.items()):
        if key != "list":
            tools[key] = clean_names(values)
    for key, values in list(databases.items()):
        if key != "list":
            databases[key] = clean_names(values)
    return result


def clean_names(values):
    if not isinstance(values, list):
        return []
    seen = set()
    cleaned = []
    for value in values:
        name = str(value).strip()
        if name and name not in seen:
            seen.add(name)
            cleaned.append(name)
    return cleaned


def tool_categories(config):
    categories = config.get("tools", {})
    return sorted(set(DEFAULT_TOOL_CATEGORIES) | {key for key in categories if key != "list"}, key=str.lower)


def names_for_type(config, resource_type):
    if resource_type == "tool":
        return config.get("tools", {}).get("list", [])
    if resource_type == "database":
        return config.get("databases", {}).get("list", [])
    if resource_type == "reference":
        return config.get("refGenomes_list", [])
    raise ToolsError("Unknown resource type: {}".format(resource_type))


def resource_catalog(config, pipelines_dir):
    dependencies = pipeline_dependencies(config, pipelines_dir)
    resources = {kind: [] for kind in RESOURCE_TYPES}
    categories = config.get("tools", {})
    for kind in RESOURCE_TYPES:
        for name in names_for_type(config, kind):
            entry = config.get(name, {})
            entry = entry if isinstance(entry, dict) else {}
            capabilities = [key for key, values in categories.items() if key != "list" and name in values]
            resources[kind].append({
                "name": name,
                "config": copy.deepcopy(entry),
                "capabilities": capabilities,
                "dependencies": dependencies.get(name, []),
                "status": resource_status(kind, entry),
            })
    return resources


def resource_status(kind, entry):
    if not isinstance(entry, dict):
        return "invalid"
    if kind == "reference":
        value = entry.get("fasta")
    else:
        container = entry.get("container")
        image = container.get("image") if isinstance(container, dict) else container
        value = entry.get("path") or image
    return "ready" if value or entry.get("path_optional") else "incomplete"


def validate_tools(config, pipelines_dir=None, previous=None):
    errors = []
    warnings = []
    if not isinstance(config, dict):
        return ["Tools configuration must contain a JSON object"], warnings
    normalized = normalize_tools(config)
    namespaces = {kind: names_for_type(normalized, kind) for kind in RESOURCE_TYPES}
    owners = {}
    for kind, names in namespaces.items():
        for name in names:
            if not NAME_PATTERN.match(name):
                errors.append("Invalid {} name: {}".format(kind, name))
            owners.setdefault(name, []).append(kind)
            entry = normalized.get(name)
            if not isinstance(entry, dict):
                errors.append("{} '{}' has no configuration object".format(kind.title(), name))
                continue
            if kind == "reference" and not str(entry.get("fasta", "")).strip():
                errors.append("Reference '{}' requires a FASTA path".format(name))
            if kind != "reference":
                container = entry.get("container")
                image = container.get("image") if isinstance(container, dict) else container
                if not str(entry.get("path", "")).strip() and not str(image or "").strip() and not entry.get("path_optional"):
                    warnings.append("{} '{}' has neither a local path nor a container image".format(kind.title(), name))
            warnings.extend(path_warnings(kind, name, entry))
    for name, kinds in owners.items():
        if len(kinds) > 1:
            errors.append("'{}' is present in multiple resource lists: {}".format(name, ", ".join(kinds)))

    listed = set(owners)
    reserved = {"tools", "databases", "refGenomes_list"}
    for name, entry in normalized.items():
        if name not in reserved and isinstance(entry, dict) and name not in listed:
            warnings.append("Configuration '{}' is not present in a resource list".format(name))
    for category, values in normalized.get("tools", {}).items():
        if category == "list":
            continue
        for name in values:
            if name not in namespaces["tool"]:
                warnings.append("Tool category '{}' references unknown tool '{}'".format(category, name))

    if previous is not None and pipelines_dir is not None:
        removed = set().union(*(set(names_for_type(previous, kind)) for kind in RESOURCE_TYPES)) - listed
        dependencies = pipeline_dependencies(previous, pipelines_dir)
        for name in sorted(removed):
            if dependencies.get(name):
                errors.append("Cannot remove '{}'; used by {}".format(name, ", ".join(dependencies[name])))
    return unique(errors), unique(warnings)


def path_warnings(kind, name, entry):
    warnings = []
    fields = ("fasta", "dict") if kind == "reference" else ("path", "local_path", "local_files", "cache_dir", "script_dir")
    for field in fields:
        value = entry.get(field)
        if not value or not os.path.isabs(str(value)):
            continue
        if field == "path" and (entry.get("container") or entry.get("container_path") == value):
            continue
        path = Path(str(value))
        if field == "fasta":
            field_label = "FASTA"
        elif field == "path":
            field_label = "executable" if kind == "tool" else "data"
        else:
            field_label = field
        if not path.exists():
            warnings.append("{} '{}': {} path does not exist".format(kind.title(), name, field_label))
        elif kind == "tool" and field == "path" and path.is_file() and path.suffix.lower() not in (".jar", ".py") and not os.access(str(path), os.X_OK) and not script_interpreter(path):
            warnings.append("Tool '{}': path is not executable and has no usable script interpreter".format(name))
    container = entry.get("container")
    if container and not isinstance(container, (dict, str)):
        warnings.append("{} '{}': container must be a string or object".format(kind.title(), name))
    elif isinstance(container, dict):
        if not container.get("image"):
            warnings.append("{} '{}': container image is missing".format(kind.title(), name))
        if container.get("engine") not in (None, "", "docker", "apptainer", "singularity"):
            warnings.append("{} '{}': unsupported container engine".format(kind.title(), name))
    return warnings


def audit_tools(config, pipelines_dir):
    errors, warnings = validate_tools(config, pipelines_dir)
    return {"valid": not errors, "errors": errors, "warnings": warnings}


def pipeline_dependencies(config, pipelines_dir):
    names = set().union(*(set(names_for_type(config, kind)) for kind in RESOURCE_TYPES))
    found = {name: [] for name in names}
    root = Path(pipelines_dir)
    if not root.exists():
        return found
    for path in sorted(root.glob("*.pipeline")):
        try:
            payload = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        values = set(walk_strings(payload))
        for name in names & values:
            found[name].append(path.name)
    return found


def walk_strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, child in value.items():
            yield str(key)
            yield from walk_strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_strings(child)


def save_tools(configs_dir, pipelines_dir, filename, config, revision=None):
    path = tools_path(configs_dir, filename)
    previous = {}
    current_revision = None
    target_mode = 0o664
    if path.exists():
        target_mode = path.stat().st_mode & 0o777
        raw = path.read_bytes()
        current_revision = hashlib.sha256(raw).hexdigest()
        if revision and revision != current_revision:
            raise ToolsError("Tools configuration changed on disk; reload it before saving")
        try:
            previous = normalize_tools(json.loads(raw.decode("utf-8")))
        except (UnicodeDecodeError, ValueError):
            raise ToolsError("Existing tools configuration is not valid JSON")
    normalized = normalize_tools(config)
    errors, warnings = validate_tools(normalized, pipelines_dir, previous=previous)
    if errors:
        raise ToolsError("\n".join(errors))
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(mode="w", dir=str(path.parent), prefix=".tools-", suffix=".tmp", delete=False)
    temporary = Path(handle.name)
    try:
        with handle:
            json.dump(normalized, handle, indent=4)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(str(temporary), target_mode)
        if path.exists():
            shutil.copy2(str(path), str(path) + ".bak")
        os.replace(str(temporary), str(path))
    except Exception:
        if temporary.exists():
            temporary.unlink()
        raise
    result = load_tools(configs_dir, pipelines_dir, str(path.relative_to(Path(configs_dir).resolve())))
    result["warnings"] = warnings
    return result


def test_resource(kind, name, entry):
    if kind not in RESOURCE_TYPES:
        raise ToolsError("Unknown resource type: {}".format(kind))
    if not isinstance(entry, dict):
        raise ToolsError("Resource configuration must be an object")
    if kind == "reference":
        fasta = str(entry.get("fasta", "")).strip()
        checks = [{"label": "FASTA", "ok": bool(fasta and Path(fasta).is_file()), "detail": fasta or "Not configured"}]
        fasta_path = Path(fasta) if fasta else None
        dictionary = str(entry.get("dict", "")).strip()
        if not dictionary and fasta_path:
            dictionary = str(fasta_path.with_suffix(".dict"))
        fasta_index = str(fasta_path) + ".fai" if fasta_path else ""
        checks.append({"label": "FASTA index", "ok": bool(fasta_index and Path(fasta_index).is_file()), "detail": fasta_index or "Not configured"})
        checks.append({"label": "Sequence dictionary", "ok": bool(dictionary and Path(dictionary).is_file()), "detail": dictionary or "Not configured"})
        return {"ok": all(item["ok"] for item in checks), "preview": fasta, "checks": checks}
    if kind == "database":
        path = str(entry.get("local_path") or entry.get("path", "")).strip()
        optional = bool(entry.get("path_optional"))
        ok = optional or bool(path and Path(path).exists())
        detail = path or ("No external path required" if optional else "Not configured")
        return {"ok": ok, "preview": path, "checks": [{"label": "Database path", "ok": ok, "detail": detail}]}

    container = entry.get("container")
    if isinstance(container, dict) and container.get("image"):
        engine = str(container.get("engine") or "docker")
        image = str(container["image"])
        executable = shutil.which(engine)
        command = [engine, "image", "inspect", image] if engine == "docker" else [engine, "inspect", image]
        if not executable:
            return {"ok": False, "preview": " ".join(command), "checks": [{"label": "Container engine", "ok": False, "detail": "{} not found".format(engine)}]}
    else:
        configured = str(entry.get("path", "")).strip()
        executable = configured if os.path.isabs(configured) else shutil.which(configured)
        suffix = Path(configured).suffix.lower()
        if suffix == ".jar":
            runtime = shutil.which("java")
            executable = configured if Path(configured).is_file() else None
            command = [str(runtime or "java"), "-jar", configured, "--version"]
        elif suffix == ".py":
            executable = configured if Path(configured).is_file() else None
            command = [sys.executable, configured, "--version"]
        else:
            command = [str(executable or configured), "--version"]
        executable_ok = bool(executable and Path(executable).is_file())
        if suffix not in (".jar", ".py"):
            executable_ok = executable_ok and os.access(executable, os.X_OK)
            if executable and not executable_ok:
                interpreter = script_interpreter(Path(executable))
                if interpreter:
                    command = [interpreter, str(executable), "--version"]
                    executable_ok = True
        if suffix == ".jar":
            executable_ok = executable_ok and bool(runtime)
        if not executable_ok:
            return {"ok": False, "preview": " ".join(command), "checks": [{"label": "Executable", "ok": False, "detail": configured or "Not configured"}]}
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=8, check=False)
        output = (completed.stdout or completed.stderr or "").strip().splitlines()
        detail = output[0][:300] if output else "Exit code {}".format(completed.returncode)
        ok = completed.returncode == 0
    except (OSError, subprocess.TimeoutExpired) as exc:
        ok, detail = False, str(exc)
    return {"ok": ok, "preview": " ".join(command), "checks": [{"label": "Configuration test", "ok": ok, "detail": detail}]}


def unique(items):
    return list(dict.fromkeys(items))


def script_interpreter(path):
    try:
        with Path(path).open("rb") as handle:
            first_line = handle.readline(256).decode("utf-8", "ignore").strip()
    except OSError:
        return None
    if not first_line.startswith("#!"):
        return None
    parts = first_line[2:].strip().split()
    if not parts:
        return None
    executable = parts[0]
    if Path(executable).name == "env" and len(parts) > 1:
        return shutil.which(parts[1])
    return executable if Path(executable).is_file() else shutil.which(Path(executable).name)
