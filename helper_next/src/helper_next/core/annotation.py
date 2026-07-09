import shlex


def normalize_vep_annotation_config(annotation_config, tools_config):
    if not isinstance(annotation_config, dict):
        return annotation_config

    vep_cfg = annotation_config.get("vep_annotation", {})
    if not isinstance(vep_cfg, dict):
        return annotation_config

    tool_name = vep_cfg.get("tool") or "VEP v.95"
    tool_cfg = vep_cfg.get(tool_name, {})
    if not isinstance(tool_cfg, dict):
        return annotation_config

    legacy_args = tool_cfg.get("args", vep_cfg.get("args", []))
    resolved = build_vep_args(legacy_args, tools_config)
    tool_cfg["resolved_args"] = shell_join(resolved)
    vep_cfg[tool_name] = tool_cfg
    annotation_config["vep_annotation"] = vep_cfg
    return annotation_config


def build_vep_args(legacy_args, tools_config):
    if isinstance(legacy_args, list):
        return filter_supported_vep_args([str(item) for item in legacy_args if str(item)])
    if not isinstance(legacy_args, dict):
        return []

    args = []
    args.extend(as_list(legacy_args.get("args")))
    args.extend(as_list(legacy_args.get("features")))
    args.extend(as_list(legacy_args.get("af")))

    assembly = legacy_args.get("assembly") or "GRCh37"
    species = legacy_args.get("species") or "homo_sapiens"
    if assembly:
        args.extend(["--assembly", assembly])
    if species:
        args.extend(["--species", species])

    args.extend(plugin_args(legacy_args.get("plugins", {}), tools_config))
    return filter_supported_vep_args([str(item) for item in args if str(item)])


def filter_supported_vep_args(args):
    unsupported_flags = {"--af_esp"}
    filtered = []
    skip_next = False
    for arg in args:
        if skip_next:
            skip_next = False
            continue
        if arg in unsupported_flags:
            continue
        filtered.append(arg)
    return filtered


def plugin_args(plugins, tools_config):
    if not isinstance(plugins, dict):
        return []

    args = []
    for plugin in as_list(plugins.get("list")):
        plugin_cfg = plugins.get(plugin, {})
        if not isinstance(plugin_cfg, dict):
            plugin_cfg = {}
        tool_cfg = tools_config.get(plugin, {})
        if not isinstance(tool_cfg, dict):
            tool_cfg = {}

        parts = [plugin]
        for value in (tool_cfg.get("path", ""), plugin_cfg.get("files", ""), plugin_cfg.get("fields", "")):
            if value:
                parts.append(str(value))
        args.extend(["--plugin", ",".join(parts)])
    return args


def as_list(value):
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        if "," in value:
            return [item.strip() for item in value.split(",") if item.strip()]
        return [value]
    return [value]


def shell_join(args):
    return " ".join(shlex.quote(str(item)) for item in args if str(item))
