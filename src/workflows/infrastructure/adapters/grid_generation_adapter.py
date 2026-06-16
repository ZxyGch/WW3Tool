"""无 GUI 网格生成适配器。

根据 ``PipelineConfig.grid.mesh_type`` 调用 meshgen 下对应生成器：

- ``structured``：pygridgen ``create_grid``；
- ``smc``：SMC 生成器子进程；
- ``unstructured``：非结构网格 JSON 驱动流程。

嵌套网格时会分别在外层 ``coarse/`` 与内层 ``fine/`` 目录产出网格文件。

[EN] Headless grid generation adapter.

Invokes the corresponding generator under meshgen based on
``PipelineConfig.grid.mesh_type``:

- ``structured``: pygridgen ``create_grid``;
- ``smc``: SMC generator subprocess;
- ``unstructured``: unstructured grid JSON-driven workflow.

For nested grids, grid files are produced in the outer ``coarse/`` and inner
``fine/`` directories respectively.
"""

from __future__ import annotations

import importlib.util
import hashlib
import json
import os
import shutil
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict

from ..runtime_config import (
    SMC_GRID_JSON_DEFAULTS,
    UNST_MSH_GEN_CONFIG_DEFAULTS,
    get_project_meshgen_path,
)

from ...domain.config_models import GridConfig, GridRegion, PipelineConfig
from ...support.logging import CoreLogger
from ...support.translations import tr
from ..grid_visualization.structured_grid_paths import (
    structured_grid_desc_basenames_to_copy,
    structured_grid_desc_path,
)


REFERENCE_DATA_REQUIRED_FILES = [
    "coastal_bound_full.mat",
    "coastal_bound_high.mat",
    "coastal_bound_inter.mat",
    "coastal_bound_low.mat",
    "coastal_bound_coarse.mat",
    "etopo1.nc",
    "etopo2.nc",
    "gebco.nc",
]


def _reference_dir(config: GridConfig) -> Path:
    if config.reference_data_path:
        return config.reference_data_path
    return Path(get_project_meshgen_path()) / "reference_data"


def _check_reference_data(ref_dir: Path) -> None:
    missing = [name for name in REFERENCE_DATA_REQUIRED_FILES if not (ref_dir / name).exists()]
    if missing:
        raise RuntimeError(
            "reference_data 缺失，无法生成网格："
            + ", ".join(missing[:5])
            + (f" 等 {len(missing)} 个文件" if len(missing) > 5 else "")
            + f"；目录：{ref_dir}"
        )


# 用户面板的测深源名称 -> pygridgen ref_grid（亦即缓存键中标识测深数据的稳定名称）。
# [EN] User panel bathymetry source name -> pygridgen ref_grid (i.e. the stable name identifying bathymetry data in cache keys).
_STRUCTURED_BATHY_MAP = {"GEBCO": "gebco", "ETOP1": "etopo1", "ETOP2": "etopo2"}


def _structured_ref_grid(settings: Any) -> str:
    return _STRUCTURED_BATHY_MAP.get(str(settings.bathymetry).upper(), "gebco")


def _pygridgen_dir() -> Path:
    return Path(get_project_meshgen_path()) / "structured_generator" / "pygridgen"


def _grid_cache_dir() -> Path:
    cache_dir = Path(get_project_meshgen_path()) / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def _unstructured_workspace_dir() -> Path:
    """返回非结构网格生成器自己的中间文件工作区。"""
    return (
        Path(get_project_meshgen_path())
        / "unstructured_generator"
        / "unst_msh_gen"
        / "mesh_workspace"
    )


def _structured_grid_mask_path(folder: Path) -> Path | None:
    primary = folder / "grid.mask_nobound"
    if primary.is_file():
        return primary
    fallback = folder / "grid.mask"
    return fallback if fallback.is_file() else None


def _file_signature(path: Path) -> list[int]:
    if path.is_file():
        st = path.stat()
        return [int(st.st_mtime_ns), int(st.st_size)]
    return [0, 0]


def _data_file_cache_identity(path_value: str) -> Dict[str, Any]:
    """Return a stable, location-independent identity for optional mesh data files."""
    if not path_value:
        return {"name": "", "size": 0}
    path = Path(str(path_value)).expanduser()
    try:
        resolved = path.resolve()
    except OSError:
        resolved = path
    size = resolved.stat().st_size if resolved.is_file() else 0
    return {"name": resolved.name, "size": int(size)}


def _stable_hash(payload: Dict[str, Any]) -> str:
    params_str = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(params_str.encode("utf-8")).hexdigest()


def _structured_cache_key(region: GridRegion, config: GridConfig) -> str:
    settings = config.structured
    backend = "python" if config.gridgen_version == "Python" else "matlab"
    payload: Dict[str, Any] = {
        "dx": float(region.dx),
        "dy": float(region.dy),
        "lon_range": [float(region.lon[0]), float(region.lon[1])],
        "lat_range": [float(region.lat[0]), float(region.lat[1])],
        "ref_grid": _structured_ref_grid(settings),
        "bathymetry": str(settings.bathymetry),
        "coastline_precision": str(settings.coastline_precision),
        "gridgen_backend": backend,
    }
    if backend == "python":
        payload["pygridgen_params"] = {
            "MIN_DIST": float(settings.min_dist),
            "CUT_OFF": float(settings.cut_off),
            "LIM_BATHY": float(settings.lim_bathy),
            "LIM_VAL": float(settings.lim_val),
            "SPLIT_LIM": float(settings.split_lim),
            "LAKE_TOL": float(settings.lake_tol),
        }
    return _stable_hash(payload)


def _check_structured_cache(cache_key: str) -> Path | None:
    cache_path = _grid_cache_dir() / cache_key
    if not cache_path.is_dir():
        return None
    required = ("grid.bot", "grid.obst")
    if not all((cache_path / name).is_file() for name in required):
        return None
    if structured_grid_desc_path(str(cache_path)) is None:
        return None
    if _structured_grid_mask_path(cache_path) is None:
        return None
    return cache_path


def _load_structured_cache(cache_path: Path, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for name in ("grid.bot", "grid.obst"):
        src = cache_path / name
        if src.is_file():
            shutil.copy2(src, output_dir / name)
    for name in structured_grid_desc_basenames_to_copy(str(cache_path)):
        shutil.copy2(cache_path / name, output_dir / name)
    mask_src = _structured_grid_mask_path(cache_path)
    if mask_src is not None:
        shutil.copy2(mask_src, output_dir / "grid.mask_nobound")


def _save_structured_cache(
    cache_key: str,
    source_dir: Path,
    region: GridRegion,
    config: GridConfig,
    ref_dir: Path,
) -> None:
    cache_path = _grid_cache_dir() / cache_key
    if cache_path.exists():
        shutil.rmtree(cache_path)
    cache_path.mkdir(parents=True, exist_ok=True)

    for name in ("grid.bot", "grid.obst"):
        src = source_dir / name
        if src.is_file():
            shutil.copy2(src, cache_path / name)
    for name in structured_grid_desc_basenames_to_copy(str(source_dir)):
        shutil.copy2(source_dir / name, cache_path / name)
    mask_src = _structured_grid_mask_path(source_dir)
    if mask_src is not None:
        shutil.copy2(mask_src, cache_path / "grid.mask_nobound")

    metadata = {
        "cache_key": cache_key,
        "source_dir": str(source_dir),
        "parameters": {
            "dx": region.dx,
            "dy": region.dy,
            "lon_range": list(region.lon),
            "lat_range": list(region.lat),
            "ref_dir": str(ref_dir),
            "bathymetry": config.structured.bathymetry,
            "coastline_precision": config.structured.coastline_precision,
            "gridgen_backend": "python" if config.gridgen_version == "Python" else "matlab",
            "pygridgen_params": {
                "MIN_DIST": config.structured.min_dist,
                "CUT_OFF": config.structured.cut_off,
                "LIM_BATHY": config.structured.lim_bathy,
                "LIM_VAL": config.structured.lim_val,
                "SPLIT_LIM": config.structured.split_lim,
                "LAKE_TOL": config.structured.lake_tol,
            },
        },
    }
    (cache_path / "params.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


@contextmanager
def _pygridgen_import_path():
    """临时将 pygridgen 目录加入 ``sys.path``，供子进程内 ``import grid`` 使用。

    [EN] Temporarily add the pygridgen directory to ``sys.path`` so that ``import grid`` works inside the subprocess.
    """
    pygridgen_dir = _pygridgen_dir()
    path_str = str(pygridgen_dir)
    inserted = path_str not in sys.path
    if inserted:
        sys.path.insert(0, path_str)
    try:
        yield pygridgen_dir
    finally:
        if inserted:
            sys.path.remove(path_str)


def _run_pygridgen_subprocess(
    pygridgen_dir: Path,
    kwargs: Dict[str, Any],
    out_dir: Path,
    logger: CoreLogger,
) -> None:
    """Spawn create_grid in a subprocess so the Python GIL is not held by the generator.

    Parameters are written to a temp JSON file; a one-liner runner reads them back
    and calls create_grid(**kwargs).  This matches the SMC / unstructured approach.
    """
    import tempfile

    module_path = pygridgen_dir / "create_grid.py"
    if not module_path.is_file():
        raise RuntimeError(f"未找到 pygridgen create_grid.py：{module_path}")

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, dir=out_dir, encoding="utf-8"
    ) as f:
        json.dump(kwargs, f)
        cfg_path = f.name

    runner = (
        "import json, sys; "
        f"sys.path.insert(0, {json.dumps(str(pygridgen_dir))}); "
        "from create_grid import create_grid; "
        f"create_grid(**json.load(open({json.dumps(cfg_path)})))"
    )
    try:
        _run_subprocess([sys.executable, "-c", runner], out_dir, logger, log_command=False)
    finally:
        try:
            os.unlink(cfg_path)
        except OSError:
            pass


def _structured_kwargs(region: GridRegion, config: GridConfig, out_dir: Path) -> Dict[str, Any]:
    ref_dir = _reference_dir(config)
    settings = config.structured
    return {
        "dx": region.dx,
        "dy": region.dy,
        "lon_range": [float(region.lon[0]), float(region.lon[1])],
        "lat_range": [min(float(region.lat[0]), float(region.lat[1])), max(float(region.lat[0]), float(region.lat[1]))],
        "out_dir": str(out_dir),
        "ref_dir": str(ref_dir),
        "ref_grid": _structured_ref_grid(settings),
        "boundary": settings.coastline_precision.lower(),
        "MIN_DIST": settings.min_dist,
        "CUT_OFF": settings.cut_off,
        "LIM_BATHY": settings.lim_bathy,
        "LIM_VAL": settings.lim_val,
        "SPLIT_LIM": settings.split_lim,
        "LAKE_TOL": settings.lake_tol,
    }


def _generate_structured(config: PipelineConfig, logger: CoreLogger, *, use_cache: bool = True) -> None:
    ref_dir = _reference_dir(config.grid)
    _check_reference_data(ref_dir)

    targets = [(config.workdir.path, config.grid.outer)]
    if config.grid.grid_type == "nested":
        assert config.grid.inner is not None
        targets = [
            (config.workdir.path / "coarse", config.grid.outer),
            (config.workdir.path / "fine", config.grid.inner),
        ]

    pygridgen_dir = _pygridgen_dir()
    for out_dir, region in targets:
        out_dir.mkdir(parents=True, exist_ok=True)
        cache_key = _structured_cache_key(region, config.grid)
        if use_cache:
            cache_path = _check_structured_cache(cache_key)
            if cache_path:
                _load_structured_cache(cache_path, out_dir)
                logger.log(tr("grid_structured_cache_hit", "✅ 找到匹配的 structured 网格缓存，已复制到：{path}").format(path=out_dir))
                continue

        logger.log(tr("grid_structured_start", "🔄 开始生成 structured 网格：{path}").format(path=out_dir))
        kwargs = _structured_kwargs(region, config.grid, out_dir)
        _run_pygridgen_subprocess(pygridgen_dir, kwargs, out_dir, logger)
        if use_cache:
            try:
                _save_structured_cache(cache_key, out_dir, region, config.grid, ref_dir)
                logger.log(tr("grid_structured_saved", "✅ 已保存 structured 网格到缓存（{key}...）").format(key=cache_key[:8]))
            except Exception as exc:
                logger.log(tr("grid_structured_save_failed", "❌ 保存 structured 网格缓存失败：{error}").format(error=exc))
        logger.log(tr("grid_structured_done", "✅ structured 网格生成完成：{path}").format(path=out_dir))


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
    return base


def _run_subprocess(cmd: list[str], cwd: Path, logger: CoreLogger, *, log_command: bool = True) -> None:
    if log_command:
        logger.log(tr("grid_exec_cmd", "▶ 执行：{cmd}").format(cmd=" ".join(cmd)))
    proc = subprocess.Popen(
        cmd,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        line = line.rstrip()
        if line:
            logger.log(line)
    ret = proc.wait()
    if ret != 0:
        raise RuntimeError(f"命令执行失败（返回码 {ret}）：{' '.join(cmd)}")


SMC_CACHE_FILES = (
    "grid_cell.dat",
    "grid.json",
    "grid_subtr.dat",
    "grid_iside.dat",
    "grid_jside.dat",
    "grid_boundary.dat",
    "grid_arctic_cells.dat",
    "grid_aisid.dat",
    "grid_ajsid.dat",
)


def _smc_cache_key(grid_dict: Dict[str, Any]) -> str:
    body = json.loads(json.dumps(grid_dict, default=str))
    output = dict(body.get("output") or {})
    output.pop("output_dir", None)
    body["output"] = output
    input_section = dict(body.get("input") or {})
    bathy_path = Path(str(input_section.get("bathymetry_file") or "")).expanduser()
    bathy_abs = bathy_path.resolve() if str(bathy_path) else Path("")
    input_section["bathymetry_file"] = str(bathy_abs).replace("\\", "/") if str(bathy_path) else ""
    body["input"] = input_section
    return _stable_hash(
        {
            "grid_body": body,
            "bathy_sig": _file_signature(bathy_abs) if str(bathy_path) else [0, 0],
        }
    )


def _check_smc_cache(cache_key: str) -> Path | None:
    cache_path = _grid_cache_dir() / "smc" / cache_key
    required = ("grid_cell.dat", "grid.json", "grid_subtr.dat", "grid_iside.dat", "grid_jside.dat")
    if all((cache_path / name).is_file() and (cache_path / name).stat().st_size > 0 for name in required):
        return cache_path
    return None


def _load_smc_cache(cache_path: Path, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for name in SMC_CACHE_FILES:
        dst = output_dir / name
        if dst.is_file():
            dst.unlink()
    for name in SMC_CACHE_FILES:
        src = cache_path / name
        if src.is_file():
            shutil.copy2(src, output_dir / name)


def _save_smc_cache(cache_key: str, output_dir: Path) -> None:
    cache_path = _grid_cache_dir() / "smc" / cache_key
    if cache_path.exists():
        shutil.rmtree(cache_path)
    cache_path.mkdir(parents=True, exist_ok=True)
    for name in SMC_CACHE_FILES:
        src = output_dir / name
        if src.is_file() and src.stat().st_size > 0:
            shutil.copy2(src, cache_path / name)
    metadata = {"cache_key": cache_key, "kind": "smc"}
    (cache_path / "params.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _unstructured_cache_key(grid_json: Dict[str, Any]) -> str:
    body = json.loads(json.dumps(grid_json, default=str))
    # 输出目录和生成器安装路径不改变网格内容，不能参与缓存键。
    # [EN] Output locations and generator installation paths do not change
    # mesh content and therefore must not participate in the cache key.
    body.pop("Output", None)
    workflow = dict(body.get("Workflow") or {})
    for key in ("unst_msh_gen_dir", "resolved_config_name", "jigsaw_python_root"):
        workflow.pop(key, None)
    body["Workflow"] = workflow
    data_files = dict(body.get("DataFiles") or {})
    data_file_identity = {
        "dem_file": _data_file_cache_identity(str(data_files.get("dem_file") or "")),
        "mask_file": _data_file_cache_identity(str(data_files.get("mask_file") or "")),
    }
    for key, identity in data_file_identity.items():
        data_files[key] = identity["name"]
    body["DataFiles"] = data_files
    return _stable_hash(
        {
            "grid": body,
            "data_files": data_file_identity,
        }
    )


def _valid_unstructured_cache_path(cache_path: Path) -> Path | None:
    grid_file = cache_path / "grid.ww3"
    if grid_file.is_file() and grid_file.stat().st_size > 0:
        return cache_path
    return None


def _legacy_unstructured_cache(cache_key: str) -> Path | None:
    cache_root = _grid_cache_dir() / "unst"
    if not cache_root.is_dir():
        return None
    for params_path in cache_root.glob("*/params.json"):
        legacy_path = params_path.parent
        if legacy_path.name == cache_key:
            continue
        try:
            metadata = json.loads(params_path.read_text(encoding="utf-8"))
            grid = metadata.get("grid")
            if not isinstance(grid, dict):
                continue
            if _unstructured_cache_key(grid) != cache_key:
                continue
        except Exception:
            continue
        if _valid_unstructured_cache_path(legacy_path):
            return legacy_path
    return None


def _check_unstructured_cache(cache_key: str) -> Path | None:
    cache_path = _grid_cache_dir() / "unst" / cache_key
    if _valid_unstructured_cache_path(cache_path):
        return cache_path

    legacy_path = _legacy_unstructured_cache(cache_key)
    if not legacy_path:
        return None

    cache_path.mkdir(parents=True, exist_ok=True)
    shutil.copy2(legacy_path / "grid.ww3", cache_path / "grid.ww3")
    legacy_params = legacy_path / "params.json"
    if legacy_params.is_file():
        try:
            metadata = json.loads(legacy_params.read_text(encoding="utf-8"))
            metadata["cache_key"] = cache_key
            metadata["migrated_from"] = legacy_path.name
            (cache_path / "params.json").write_text(
                json.dumps(metadata, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        except Exception:
            shutil.copy2(legacy_params, cache_path / "params.json")
    return cache_path


def _load_unstructured_cache(cache_path: Path, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(cache_path / "grid.ww3", output_dir / "grid.ww3")


def _save_unstructured_cache(cache_key: str, grid_file: Path, grid_json: Dict[str, Any]) -> None:
    cache_path = _grid_cache_dir() / "unst" / cache_key
    if cache_path.exists():
        shutil.rmtree(cache_path)
    cache_path.mkdir(parents=True, exist_ok=True)
    shutil.copy2(grid_file, cache_path / "grid.ww3")
    metadata = {"cache_key": cache_key, "grid": grid_json}
    (cache_path / "params.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _generate_smc(config: PipelineConfig, logger: CoreLogger, *, use_cache: bool = True) -> None:
    root = Path(get_project_meshgen_path())
    smc_dir = root / "smc_generator"
    cfg = json.loads(json.dumps(SMC_GRID_JSON_DEFAULTS))
    settings = config.grid.smc
    smc_bathy_map = {
        "GEBCO": "gebco.nc",
        "ETOPO1": "etopo1.nc",
        "ETOP1": "etopo1.nc",
        "ETOPO2": "etopo2.nc",
        "ETOP2": "etopo2.nc",
    }
    cfg["input"]["bathymetry_file"] = str(_reference_dir(config.grid) / smc_bathy_map[settings.bathymetry])
    cfg["input"]["bathy_convention"] = settings.bathy_convention
    cfg["grid"]["n_levels"] = settings.n_levels
    cfg["physics"].update(
        {
            "wlevel": settings.wlevel,
            "depmin": settings.depmin,
            "dshalw": settings.dshalw,
        }
    )
    cfg["boundary"].update(
        {
            "generate_boundary_cells": settings.generate_boundary_cells,
            "msea": settings.msea,
        }
    )
    _deep_merge(cfg, settings.options)
    _deep_merge(cfg, config.grid.options or {})
    bathy = str(cfg.get("input", {}).get("bathymetry_file") or "")
    if bathy and not Path(bathy).is_absolute():
        cfg["input"]["bathymetry_file"] = str((smc_dir / bathy).resolve())
    region = config.grid.outer
    cfg["grid"]["regional_bounds"] = {
        "west_lon": float(region.lon[0]),
        "east_lon": float(region.lon[1]),
        "south_lat": float(region.lat[0]),
        "north_lat": float(region.lat[1]),
    }
    cfg["grid"].setdefault("regional_bounds_policy", "warn")
    cfg["output"]["output_dir"] = str(config.workdir.path)

    config.workdir.path.mkdir(parents=True, exist_ok=True)
    run_config = config.workdir.path / "smc_grid.json"
    run_config.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    cache_key = _smc_cache_key(cfg)
    if use_cache:
        cache_path = _check_smc_cache(cache_key)
        if cache_path:
            _load_smc_cache(cache_path, config.workdir.path)
            logger.log(tr("grid_smc_cache_hit", "✅ 找到匹配的 SMC 网格缓存，已复制到：{path}").format(path=config.workdir.path))
            return

    logger.log(tr("grid_smc_start", "🔄 开始生成 SMC 网格...") if not use_cache else tr("grid_smc_cache_miss", "ℹ️ 未找到匹配的 SMC 网格缓存，开始生成新网格..."))
    _run_subprocess([sys.executable, "create_grid.py", "--config", str(run_config)], smc_dir, logger)
    if use_cache:
        try:
            _save_smc_cache(cache_key, config.workdir.path)
            logger.log(tr("grid_smc_saved", "✅ 已保存 SMC 网格到缓存（{key}...）").format(key=cache_key[:8]))
        except Exception as exc:
            logger.log(tr("grid_smc_save_failed", "❌ 保存 SMC 网格缓存失败：{error}").format(error=exc))


def _generate_unstructured(config: PipelineConfig, logger: CoreLogger, *, use_cache: bool = True) -> None:
    root = Path(get_project_meshgen_path())
    unst_dir = root / "unstructured_generator"
    mesh_workspace = _unstructured_workspace_dir()
    unst_msh_gen_abs = str(unst_dir / "unst_msh_gen")
    jigsaw_root_abs = str(unst_dir / "jigsaw-python")
    base = json.loads(json.dumps(UNST_MSH_GEN_CONFIG_DEFAULTS))
    settings = config.grid.unstructured
    base["spacing"].update(
        {
            "hmax": settings.hmax,
            "hshr": settings.hshr,
            "hmin": settings.hmin if settings.hmin is not None else UNST_MSH_GEN_CONFIG_DEFAULTS["spacing"]["hmin"],
            "nwav": settings.nwav,
            "dhdx": settings.dhdx,
            "deep_ocean_threshold_m": settings.deep_ocean_threshold_m,
        }
    )
    base["mesh_settings"]["hfun_hmax"] = settings.hmax
    base["regional"].update(
        {
            "margin_deg": settings.margin_deg,
            "edge_segments": settings.edge_segments,
        }
    )
    _deep_merge(base, settings.options)
    _deep_merge(base, config.grid.options or {})
    # 确保一级字段优先于 options.spacing 中的同名键（向后兼容旧 params.yml）
    # [EN] Ensure top-level fields take priority over options.spacing duplicates (backward compat)
    base["spacing"].update(
        {
            "hmax": settings.hmax,
            "hshr": settings.hshr,
            "hmin": settings.hmin if settings.hmin is not None else UNST_MSH_GEN_CONFIG_DEFAULTS["spacing"]["hmin"],
            "nwav": settings.nwav,
            "dhdx": settings.dhdx,
            "deep_ocean_threshold_m": settings.deep_ocean_threshold_m,
        }
    )
    base["mesh_settings"]["hfun_hmax"] = settings.hmax
    dem = str(base.get("data", {}).get("dem_file") or "")
    mask = str(base.get("data", {}).get("mask_file") or "")
    if config.grid.reference_data_path and dem == UNST_MSH_GEN_CONFIG_DEFAULTS["data"]["dem_file"]:
        dem = str(config.grid.reference_data_path / Path(dem).name)
        base["data"]["dem_file"] = dem
    if dem and not Path(dem).is_absolute():
        base["data"]["dem_file"] = str((unst_dir / dem).resolve())
    if mask and not Path(mask).is_absolute():
        base["data"]["mask_file"] = str((unst_dir / mask).resolve())
    region = config.grid.outer
    base["regional"].update(
        {
            "lon_min": float(region.lon[0]),
            "lon_max": float(region.lon[1]),
            "lat_min": float(region.lat[0]),
            "lat_max": float(region.lat[1]),
        }
    )
    grid_json = {
        "Domain": {
            "clip_to_bounds": False,
            "west_lon": base["regional"]["lon_min"],
            "east_lon": base["regional"]["lon_max"],
            "south_lat": base["regional"]["lat_min"],
            "north_lat": base["regional"]["lat_max"],
        },
        "Regional": base["regional"],
        "Spacing": base["spacing"],
        "MeshSettings": {
            "hfun_hmax": base["mesh_settings"].get("hfun_hmax", 100.0),
            "mesh_file": "grid.msh",
            "ww3_mesh_file": "grid.ww3",
        },
        "CommandLineArgs": base["command_line_args"],
        "DataFiles": base["data"],
        "Output": {
            "mesh_workspace_dir": str(mesh_workspace),
            "ww3_publish_dir": str(config.workdir.path),
            "ww3_publish_basename": "grid.ww3",
        },
        "Workflow": {
            "run_window_mask": False,
            "unst_msh_gen_dir": unst_msh_gen_abs,
            "resolved_config_name": ".grid_run.ini",
            "jigsaw_python_root": jigsaw_root_abs,
        },
    }
    config.workdir.path.mkdir(parents=True, exist_ok=True)
    run_config = config.workdir.path / "unstructured_grid.json"
    run_config.write_text(json.dumps(grid_json, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    cache_key = _unstructured_cache_key(grid_json)
    if use_cache:
        cache_path = _check_unstructured_cache(cache_key)
        if cache_path:
            _load_unstructured_cache(cache_path, config.workdir.path)
            logger.log(tr("grid_unst_cache_hit", "✅ 找到匹配的非结构网格缓存，已复制到：{path}").format(path=config.workdir.path))
            return

    logger.log(tr("grid_unst_start", "🔄 开始生成非结构网格...") if not use_cache else tr("grid_unst_cache_miss", "ℹ️ 未找到匹配的非结构网格缓存，开始生成新网格..."))
    mesh_workspace.mkdir(parents=True, exist_ok=True)
    _run_subprocess([sys.executable, "create_grid.py", "--grid", str(run_config)], unst_dir, logger)
    produced = config.workdir.path / "grid.ww3"
    fallback = unst_dir / "output" / "grid.ww3"
    if not produced.exists() and fallback.exists():
        shutil.copy2(fallback, produced)
    if use_cache and produced.is_file() and produced.stat().st_size > 0:
        try:
            _save_unstructured_cache(cache_key, produced, grid_json)
            logger.log(tr("grid_unst_saved", "✅ 已保存非结构网格到缓存（{key}...）").format(key=cache_key[:12]))
        except Exception as exc:
            logger.log(tr("grid_unst_save_failed", "❌ 保存非结构网格缓存失败：{error}").format(error=exc))


def generate_grid(config: PipelineConfig, logger: CoreLogger, *, use_cache: bool = True) -> None:
    """按配置生成 WW3 网格并写入工作目录。

    参数:
        config: 含网格类型、区域范围与工作目录的流水线配置
        logger: 用于输出生成进度与外部命令日志

    异常:
        RuntimeError: 参考数据缺失、外部命令失败或不支持的 ``mesh_type``

    [EN] Generate a WW3 grid according to the configuration and write it to the working directory.

    Args:
        config: Pipeline configuration containing grid type, region extent, and working directory
        logger: Logger for outputting generation progress and external command logs

    Raises:
        RuntimeError: Reference data missing, external command failure, or unsupported ``mesh_type``
    """
    if config.grid.mesh_type == "structured":
        _generate_structured(config, logger, use_cache=use_cache)
    elif config.grid.mesh_type == "smc":
        _generate_smc(config, logger, use_cache=use_cache)
    elif config.grid.mesh_type == "unstructured":
        _generate_unstructured(config, logger, use_cache=use_cache)
    else:
        raise RuntimeError(f"不支持的网格类型：{config.grid.mesh_type}")
