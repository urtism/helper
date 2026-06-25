from __future__ import annotations

import json
import shlex
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ToolInput:
    name: str
    path: str = ""
    kind: str = "file"
    optional: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolOutput:
    name: str
    path: str = ""
    kind: str = "file"
    optional: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ContainerSpec:
    engine: str = "none"
    image: str = ""
    bind_mounts: List[str] = field(default_factory=list)
    workdir: str = ""
    env: Dict[str, str] = field(default_factory=dict)
    extra_args: List[str] = field(default_factory=list)

    @classmethod
    def from_tool_config(cls, tool_config: Dict[str, Any]) -> Optional["ContainerSpec"]:
        if not isinstance(tool_config, dict):
            return None

        raw = tool_config.get("container")
        image = tool_config.get("image", "")
        if isinstance(raw, dict):
            image = raw.get("image", image)
            engine = raw.get("engine") or ("docker" if image else "none")
            spec = cls(
                engine=engine,
                image=image,
                bind_mounts=_string_list(raw.get("bind_mounts", raw.get("bind", []))),
                workdir=str(raw.get("workdir", "")),
                env=_string_dict(raw.get("env", {})),
                extra_args=_string_list(raw.get("extra_args", raw.get("args", []))),
            )
        elif raw or image:
            raw_text = str(raw or "")
            spec = cls(
                engine="docker" if (image or raw_text) else "none",
                image=str(image or raw_text),
            )
        else:
            return None

        if spec.engine == "none" and not spec.image:
            return None
        return spec


@dataclass
class ToolInvocation:
    tool: str
    executable: str
    version: str = ""
    command_args: List[str] = field(default_factory=list)
    command_preview: str = ""
    inputs: List[ToolInput] = field(default_factory=list)
    outputs: List[ToolOutput] = field(default_factory=list)
    container: Optional[ContainerSpec] = None
    env: Dict[str, str] = field(default_factory=dict)
    resources: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.command_preview:
            self.command_preview = shell_join([self.executable] + self.command_args)

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        if self.container is None:
            payload["container"] = None
        return payload

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True)


class ToolWrapper:
    logical_name = ""
    default_operation = ""

    def __init__(
        self,
        operation_config: Optional[Dict[str, Any]] = None,
        tool_config: Optional[Dict[str, Any]] = None,
        panel_design: Optional[Dict[str, Any]] = None,
        reference_info: Optional[Dict[str, Any]] = None,
        tools_config: Optional[Dict[str, Any]] = None,
    ):
        self.operation_config = operation_config if isinstance(operation_config, dict) else {}
        self.tool_config = tool_config if isinstance(tool_config, dict) else {}
        self.panel_design = panel_design if isinstance(panel_design, dict) else {}
        self.reference_info = reference_info if isinstance(reference_info, dict) else {}
        self.tools_config = tools_config if isinstance(tools_config, dict) else {}

    def build(self, tool_name: str, operation_name: Optional[str] = None) -> ToolInvocation:
        operation = operation_name or self.default_operation
        args = self.command_args(operation)
        invocation = ToolInvocation(
            tool=tool_name,
            executable=self.executable(tool_name),
            version=str(self.tool_config.get("version", self.tool_config.get("versione", ""))),
            command_args=[str(item) for item in args if str(item)],
            inputs=self.inputs(operation),
            outputs=self.outputs(operation),
            container=ContainerSpec.from_tool_config(self.tool_config),
            env=self.env(),
            resources=self.resources(),
            metadata=self.metadata(operation),
        )
        return invocation

    def executable(self, tool_name: str) -> str:
        return str(self.tool_config.get("path") or tool_name)

    def command_args(self, operation: str) -> List[str]:
        return config_args(self.operation_config)

    def inputs(self, operation: str) -> List[ToolInput]:
        return []

    def outputs(self, operation: str) -> List[ToolOutput]:
        return []

    def env(self) -> Dict[str, str]:
        return _string_dict(self.tool_config.get("env", self.tool_config.get("environment", {})))

    def resources(self) -> Dict[str, Any]:
        resources = {}
        for key in ("threads", "ram", "cpus", "memory", "time"):
            value = self.operation_config.get(key, self.tool_config.get(key))
            if value not in (None, "", []):
                resources[key] = value
        return resources

    def metadata(self, operation: str) -> Dict[str, Any]:
        return {
            "operation": operation,
            "resolved_by": self.__class__.__name__,
        }

    def panel_assets(self) -> Dict[str, Any]:
        assets = self.panel_design.get("assets", {})
        return assets if isinstance(assets, dict) else {}

    def reference_fasta(self) -> str:
        return str(self.reference_info.get("fasta", ""))


def config_args(config: Dict[str, Any]) -> List[str]:
    args = config.get("resolved_args", config.get("args", []))
    if isinstance(args, str):
        return shlex.split(args)
    if isinstance(args, (list, tuple)):
        return [str(item) for item in args if str(item)]
    return []


def shell_join(args: List[str]) -> str:
    return " ".join(shlex.quote(str(item)) for item in args if str(item))


def _string_list(value: Any) -> List[str]:
    if value in (None, ""):
        return []
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value if str(item)]
    return [str(value)]


def _string_dict(value: Any) -> Dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {str(key): str(item) for key, item in value.items() if item not in (None, "")}
