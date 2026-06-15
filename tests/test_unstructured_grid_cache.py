from copy import deepcopy
from pathlib import Path

from workflows.infrastructure.adapters.grid_generation_adapter import (
    _unstructured_cache_key,
    _unstructured_workspace_dir,
)
from workflows.infrastructure.runtime_config import get_project_meshgen_path


def _grid_json() -> dict:
    return {
        "Domain": {"west_lon": 110.0, "east_lon": 130.0},
        "Spacing": {"hmax": 60.0, "hmin": 3.0},
        "DataFiles": {"dem_file": "", "mask_file": ""},
        "Output": {
            "mesh_workspace_dir": "/tmp/work-a/mesh_workspace",
            "ww3_publish_dir": "/tmp/work-a",
            "ww3_publish_basename": "grid.ww3",
        },
        "Workflow": {
            "run_window_mask": False,
            "unst_msh_gen_dir": "/install-a/unst_msh_gen",
            "resolved_config_name": ".grid_run.ini",
            "jigsaw_python_root": "/install-a/jigsaw-python",
        },
    }


def test_unstructured_cache_key_ignores_runtime_and_output_paths() -> None:
    first = _grid_json()
    second = deepcopy(first)
    second["Output"]["mesh_workspace_dir"] = "/tmp/work-b/mesh_workspace"
    second["Output"]["ww3_publish_dir"] = "/tmp/work-b"
    second["Workflow"]["unst_msh_gen_dir"] = "/install-b/unst_msh_gen"
    second["Workflow"]["jigsaw_python_root"] = "/install-b/jigsaw-python"

    assert _unstructured_cache_key(first) == _unstructured_cache_key(second)


def test_unstructured_cache_key_changes_with_mesh_parameters() -> None:
    first = _grid_json()
    second = deepcopy(first)
    second["Spacing"]["hmin"] = 5.0

    assert _unstructured_cache_key(first) != _unstructured_cache_key(second)


def test_unstructured_workspace_stays_inside_mesh_generator() -> None:
    expected = (
        Path(get_project_meshgen_path())
        / "unstructured_generator"
        / "unst_msh_gen"
        / "mesh_workspace"
    )

    assert _unstructured_workspace_dir() == expected
