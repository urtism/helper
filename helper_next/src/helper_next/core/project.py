from pathlib import Path
from typing import NamedTuple, Optional, Tuple, List


class ProjectPaths(NamedTuple):
    root: Path
    configs: Path
    pipelines: Path
    files: Path
    scripts: Path


def find_repo_root(start=None):
    # type: (Optional[Path]) -> Path
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / "Helper.py").exists() and (candidate / "configs").is_dir():
            return candidate
    raise RuntimeError("Could not find Helper repository root")


def get_project_paths(root=None):
    # type: (Optional[Path]) -> ProjectPaths
    repo_root = find_repo_root(root)
    return ProjectPaths(
        root=repo_root,
        configs=repo_root / "configs",
        pipelines=repo_root / "configs" / "pipelines",
        files=repo_root / "files",
        scripts=repo_root / "scripts",
    )


def list_named_files(path, suffixes):
    # type: (Path, Tuple[str, ...]) -> List[str]
    if not path.exists():
        return []
    return sorted(
        item.name
        for item in path.iterdir()
        if item.is_file() and item.name.endswith(suffixes)
    )
