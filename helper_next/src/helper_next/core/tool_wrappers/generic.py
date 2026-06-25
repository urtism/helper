from __future__ import annotations

from pathlib import Path

from helper_next.core.tool_wrappers.base import ToolInput, ToolInvocation, ToolOutput, ToolWrapper, config_args
from helper_next.core.tool_wrappers.catalog import operation_spec


class CatalogToolWrapper(ToolWrapper):
    def build(self, tool_name: str, operation_name: str | None = None) -> ToolInvocation:
        self.spec = operation_spec(operation_name or self.default_operation or tool_name)
        return super().build(tool_name, operation_name or (self.spec.operation if self.spec else ""))

    def executable(self, tool_name: str) -> str:
        if self.spec and self.spec.tool_family == "HELPER_SCRIPT":
            return str(self.tool_config.get("interpreter") or self.tool_config.get("path") or "python")
        return super().executable(tool_name)

    def command_args(self, operation):
        if not self.spec:
            return config_args(self.operation_config)
        args = []
        if self.spec.tool_family == "HELPER_SCRIPT":
            args.append(self.script_path())
            args.extend(self.script_args())
        else:
            args.extend(self.spec.command_args)
            args.extend(config_args(self.operation_config))
        return [self.resolve_token(item) for item in args if self.resolve_token(item)]

    def inputs(self, operation):
        if not self.spec:
            return []
        return [ToolInput(name, self.resolve_token(path), optional=path.startswith("{")) for name, path in self.spec.inputs.items()]

    def outputs(self, operation):
        if not self.spec:
            return []
        return [ToolOutput(name, self.resolve_token(path), optional=path.startswith("{")) for name, path in self.spec.outputs.items()]

    def metadata(self, operation):
        metadata = super().metadata(operation)
        if self.spec:
            metadata.update(self.spec.metadata)
            metadata["tool_family"] = self.spec.tool_family
            metadata["catalog_operation"] = self.spec.operation
        metadata["declarative_only"] = True
        return metadata

    def script_path(self):
        script = self.spec.metadata.get("script", "") if self.spec else ""
        configured = self.tool_config.get("script") or self.tool_config.get("path")
        if configured and str(configured).endswith(script):
            return str(configured)
        scripts_dir = self.tool_config.get("scripts_dir") or self.operation_config.get("scripts_dir") or "scripts"
        return str(Path(str(scripts_dir)) / script)

    def script_args(self):
        raw = self.operation_config.get("script_args", self.operation_config.get("params", {}))
        if isinstance(raw, dict):
            args = []
            for key, value in raw.items():
                flag = str(key)
                if not flag.startswith("-"):
                    flag = "--{}".format(flag)
                if value is True:
                    args.append(flag)
                elif value not in (False, None, ""):
                    args.extend([flag, str(value)])
            return args
        return config_args({"args": raw})

    def resolve_token(self, value):
        text = str(value)
        replacements = self.replacements()
        for key, replacement in replacements.items():
            text = text.replace("{" + key + "}", str(replacement))
        return text

    def replacements(self):
        assets = self.panel_assets()
        replacements = {
            "threads": self.operation_config.get("threads", self.tool_config.get("threads", "{threads}")),
            "ram": self.operation_config.get("ram", self.tool_config.get("ram", "{ram}")),
            "reference_fasta": self.operation_config.get("reference_fasta") or self.reference_fasta() or "{reference_fasta}",
            "reference_index": self.operation_config.get("reference_index") or self.reference_info.get("bowtie2_index") or "{reference_index}",
            "target_bed": self.operation_config.get("target_bed") or self.operation_config.get("target_intervals") or assets.get("target_bed", "{target_bed}"),
            "transcripts_list": self.operation_config.get("transcripts_list") or assets.get("transcripts_list", "{transcripts_list}"),
        }
        for key, value in self.operation_config.items():
            if value not in (None, "", []):
                replacements[str(key)] = value
        return replacements


def build_catalog_invocation(operation_name, tool_name, operation_config, tool_config, panel_design=None, reference_info=None, tools_config=None):
    if not operation_spec(operation_name):
        return None
    wrapper = CatalogToolWrapper(operation_config, tool_config, panel_design, reference_info, tools_config)
    return wrapper.build(tool_name, operation_name)
