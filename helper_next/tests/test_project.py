from pathlib import Path

from helper_next.api.app import list_gene_panel_designs, load_gene_panel_design_details
from helper_next.core.project import get_project_paths


def test_get_project_paths_from_repo_root():
    root = Path(__file__).resolve().parents[2]
    paths = get_project_paths(root)

    assert paths.root == root
    assert paths.configs.name == "configs"
    assert paths.pipelines.name == "pipelines"


def test_gene_panel_designs_are_loaded_from_experiment_list(tmp_path):
    configs = tmp_path / "configs"
    configs.mkdir()
    (configs / "experiment_list.cfg").write_text(
        """
        {
          "list": ["Panel B", "Panel A", "Broken Panel"],
          "Panel B": {"panel_name": "Panel B", "target_bed": "/targets/b.bed"},
          "Panel A": {"panel_name": "Panel A", "target_bed": "/targets/a.bed"},
          "Broken Panel": {"panel_name": "Broken Panel", "target_bed": ""}
        }
        """
    )

    assert list_gene_panel_designs(configs) == ["Panel B", "Panel A"]

    details = load_gene_panel_design_details(configs)
    assert details["designs"]["Panel B"]["assets"]["target_bed"] == "/targets/b.bed"
    assert details["designs"]["Panel A"]["display_name"] == "Panel A"
    assert details["invalid"]["Broken Panel"] == ["target_bed is required"]
