from copy import deepcopy
import json
import os
from pathlib import Path

from workflows.infrastructure.adapters.grid_generation_adapter import (
    _check_unstructured_cache,
    _data_file_cache_identity,
    _unstructured_cache_key,
    _unstructured_workspace_dir,
)
import workflows.infrastructure.adapters.grid_generation_adapter as grid_adapter
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


def test_unstructured_cache_key_ignores_data_file_location_with_same_identity() -> None:
    first = _grid_json()
    second = deepcopy(first)
    first["DataFiles"]["dem_file"] = "/install-a/reference/RTopo.nc"
    second["DataFiles"]["dem_file"] = "/install-b/reference/RTopo.nc"

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


def test_data_file_cache_identity_ignores_mtime(tmp_path: Path) -> None:
    data_file = tmp_path / "RTopo.nc"
    data_file.write_bytes(b"abc")
    first = _data_file_cache_identity(str(data_file))

    os.utime(data_file, (data_file.stat().st_atime + 100, data_file.stat().st_mtime + 100))
    second = _data_file_cache_identity(str(data_file))

    assert first == second == {"name": "RTopo.nc", "size": 3}


def test_unstructured_cache_check_migrates_legacy_key(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(grid_adapter, "get_project_meshgen_path", lambda: tmp_path)

    grid = _grid_json()
    cache_key = _unstructured_cache_key(grid)
    legacy_dir = tmp_path / "cache" / "unst" / "legacy-key"
    legacy_dir.mkdir(parents=True)
    (legacy_dir / "grid.ww3").write_text("grid", encoding="utf-8")
    (legacy_dir / "params.json").write_text(
        json.dumps({"cache_key": "legacy-key", "grid": grid}) + "\n",
        encoding="utf-8",
    )

    cache_path = _check_unstructured_cache(cache_key)

    assert cache_path == tmp_path / "cache" / "unst" / cache_key
    assert (cache_path / "grid.ww3").read_text(encoding="utf-8") == "grid"
