from pathlib import Path

from helper_next.core.project import get_project_paths


def test_get_project_paths_from_repo_root():
    root = Path(__file__).resolve().parents[2]
    paths = get_project_paths(root)

    assert paths.root == root
    assert paths.configs.name == "configs"
    assert paths.pipelines.name == "pipelines"
