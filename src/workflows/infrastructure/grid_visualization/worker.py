#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
网格可视化子进程：非结构 grid.ww3（Gmsh）、结构化 grid.nml（WW3 描述）/ bot / mask / obst，以及 SMC 的 grid_cell.dat + 输出目录中的 grid.json（运行配置，或由旧版元数据格式兼容）。
生成图片到 <grid_dir>/photo/grid/，并写入 .grid_viz_cache.json 供主进程跳过未改网格。

[EN] Grid visualization subprocess: unstructured grid.ww3 (Gmsh), structured grid.nml
(WW3 description) / bot / mask / obst, and SMC grid_cell.dat + grid.json in the output
directory (run configuration, or legacy metadata format compatibility).
Generates images to <grid_dir>/photo/grid/ and writes .grid_viz_cache.json so the main
process can skip unchanged grids.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import platform
import sys

import glob
import numpy as np

CACHE_FILE = ".grid_viz_cache.json"
CACHE_VERSION = 20
VIZ_PREFIX = "WW3TOOL_VIZ"


def _ensure_worker_language() -> None:
    return None


def _viz_tr(key: str, default: str) -> str:
    try:
        from ...support.translations import tr

        return tr(key, default)
    except Exception:
        return default
# 结构线框：按「边」抽样而非按「三角形」抽样，避免随机抽三角形导致邻边缺失、看起来像碎块。
# [EN] Structure wireframe: sample by "edges" rather than "triangles" to avoid random triangle sampling
# causing missing adjacent edges that look like fragmented pieces.
STRUCTURE_MAX_EDGES = 800_000
STRUCTURED_MAX_LINES = 400
# 导出 PNG 分辨率（提高 DPI 与画布尺寸以改善抽屉/放大查看时的清晰度）
# [EN] Output PNG resolution (increased DPI and canvas size for better clarity when zooming in)
OUTPUT_DPI = 300


def _configure_matplotlib_cjk_fonts() -> None:
    """Figure 标题/色标含中文时，默认 DejaVu Sans 无 CJK 会缺字；优先使用系统常见中日韩字体。

    [EN] When figure titles/colorbars contain Chinese characters, the default DejaVu Sans lacks
    CJK glyphs; prefer common system CJK fonts to avoid missing characters.
    """
    import matplotlib

    sysname = platform.system()
    if sysname == "Darwin":
        cjk_first = [
            "PingFang SC",
            "Hiragino Sans GB",
            "Heiti SC",
            "STHeiti",
            "Songti SC",
            "Arial Unicode MS",
        ]
    elif sysname == "Windows":
        cjk_first = [
            "Microsoft YaHei",
            "Microsoft JhengHei",
            "SimHei",
            "SimSun",
        ]
    else:
        cjk_first = [
            "Noto Sans CJK SC",
            "Noto Sans CJK JP",
            "WenQuanYi Zen Hei",
            "WenQuanYi Micro Hei",
            "Source Han Sans SC",
        ]
    base = matplotlib.rcParams.get("font.sans-serif")
    if isinstance(base, str):
        rest = [base]
    else:
        rest = list(base)
    merged: list[str] = []
    for f in cjk_first + rest:
        if f and f not in merged:
            merged.append(f)
    matplotlib.rcParams["font.sans-serif"] = merged
    matplotlib.rcParams["axes.unicode_minus"] = False


def emit_log(msg: str) -> None:
    """向 stdout 输出 ``WW3TOOL_VIZ\\tLOG\\t`` 协议行，供父进程解析。

    [EN] Emit a ``WW3TOOL_VIZ\\tLOG\\t`` protocol line to stdout for the parent process to parse.
    """
    print(f"{VIZ_PREFIX}\tLOG\t{msg}", flush=True)


def emit_result(obj: dict) -> None:
    """向 stdout 输出 ``WW3TOOL_VIZ\\tRESULT\\t`` JSON 结果行。

    [EN] Emit a ``WW3TOOL_VIZ\\tRESULT\\t`` JSON result line to stdout.
    """
    print(f"{VIZ_PREFIX}\tRESULT\t{json.dumps(obj, ensure_ascii=False)}", flush=True)


def _stat_fp(path: str) -> dict | None:
    if not os.path.isfile(path):
        return None
    st = os.stat(path)
    return {"mtime_ns": st.st_mtime_ns, "size": st.st_size}


def _structured_mask_path(grid_dir: str) -> str | None:
    """Use ``grid.mask_nobound`` if present; otherwise ``grid.mask``."""
    p = os.path.join(grid_dir, "grid.mask_nobound")
    if os.path.isfile(p):
        return p
    p2 = os.path.join(grid_dir, "grid.mask")
    return p2 if os.path.isfile(p2) else None


def _flat_grid_meta_ok(path: str) -> bool:
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            c = f.read(8000)
    except OSError:
        return False
    rect_ok = all(
        s in c for s in ("RECT%NX", "RECT%NY", "RECT%SX", "RECT%SY", "RECT%X0", "RECT%Y0")
    )
    curv_ok = all(
        s in c
        for s in (
            "CURV%NX",
            "CURV%NY",
            "CURV%XCOORD%FILENAME",
            "CURV%YCOORD%FILENAME",
        )
    )
    return rect_ok or curv_ok


def _structured_grid_desc_path(grid_dir: str) -> str | None:
    """Match ``structured_grid_paths.structured_grid_desc_path`` (no package import)."""
    if not grid_dir or not os.path.isdir(grid_dir):
        return None
    gm = os.path.join(grid_dir, "grid.meta")
    if os.path.isfile(gm) and _flat_grid_meta_ok(gm):
        return gm
    gn = os.path.join(grid_dir, "grid.nml")
    if os.path.isfile(gn):
        try:
            with open(gn, encoding="utf-8", errors="ignore") as f:
                ch = f.read(16000)
        except OSError:
            ch = ""
        if "&DEPTH_NML" in ch or "$ Define grid" in ch:
            return gn
    preferred = os.path.join(grid_dir, "ww3_grid.nml.grid")
    if os.path.isfile(preferred):
        return preferred
    cands = sorted(glob.glob(os.path.join(grid_dir, "ww3_grid.nml.*")))
    if cands:
        return cands[0]
    if os.path.isfile(gm):
        try:
            rpath = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rect_grid_desc_parse.py")
            spec = importlib.util.spec_from_file_location("_rgd_chk", rpath)
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                if mod.parse_rect_grid_description(gm):
                    return gm
        except Exception:
            pass
    return None


def _is_smc_legacy_run_metadata(doc: object) -> bool:
    """旧版 create_grid 写入的元数据：顶层含 cells_file、bathymetry_file 等。

    [EN] Legacy metadata written by create_grid: top-level contains cells_file, bathymetry_file, etc.
    """
    if not isinstance(doc, dict):
        return False
    if not isinstance(doc.get("cells_file"), str) or not str(doc.get("cells_file", "")).strip():
        return False
    bf = doc.get("bathymetry_file")
    return isinstance(bf, str) and bool(str(bf).strip())


def _is_smc_flat_config_doc(doc: object) -> bool:
    """与 smc_generator 输入一致的平铺 grid.json（input/grid/physics/…）。

    [EN] Flat grid.json consistent with smc_generator input (input/grid/physics/...).
    """
    if not isinstance(doc, dict):
        return False
    inp = doc.get("input")
    grid = doc.get("grid")
    if not isinstance(inp, dict) or not isinstance(grid, dict):
        return False
    if not str(inp.get("bathymetry_file") or "").strip():
        return False
    return "n_levels" in grid


def _smc_pick_nc_var(ds, configured, candidates: list[str], label: str) -> str:
    if isinstance(configured, str) and configured:
        if configured not in ds.variables:
            raise ValueError(f"SMC viz: {label} variable {configured!r} not in NetCDF")
        return configured
    for name in candidates:
        if name in ds.variables:
            return name
    raise ValueError(
        f"SMC viz: could not auto-detect {label} in NetCDF; set input.lon_var/lat_var/bathy_var in grid.json"
    )


def _smc_resolve_bathy_for_smc_viz(raw: str, grid_dir: str) -> str:
    r = (raw or "").strip()
    if not r:
        return ""
    if os.path.isabs(r) and os.path.isfile(r):
        return r
    abs_grid = os.path.abspath(os.path.normpath(grid_dir))
    tried_bases = [abs_grid, os.path.dirname(abs_grid)]
    gp = os.path.dirname(abs_grid)
    tried_bases.append(os.path.normpath(os.path.join(gp, "..")))
    tried_bases.append(os.path.normpath(os.path.join(gp, "..", "..")))
    for base in tried_bases:
        cand = os.path.normpath(os.path.join(base, r))
        if os.path.isfile(cand):
            return cand
    return os.path.normpath(os.path.join(abs_grid, r))


def _smc_flat_config_to_run_info(doc: dict, grid_dir: str) -> dict:
    """将输出目录内复制的平铺 grid.json 转成可视化使用的内部结构（含 grid_json 与 dlon/dlat）。

    [EN] Convert the flat grid.json copied into the output directory into an internal structure
    for visualization (containing grid_json and dlon/dlat).
    """
    inp = doc.get("input") or {}
    raw_bathy = str(inp.get("bathymetry_file") or "").strip()
    bathy_path = _smc_resolve_bathy_for_smc_viz(raw_bathy, grid_dir)
    if not bathy_path or not os.path.isfile(bathy_path):
        raise ValueError(f"SMC viz: bathymetry file not found ({raw_bathy!r})")

    import netCDF4 as nc

    with nc.Dataset(bathy_path, "r") as ds:
        lon_var = _smc_pick_nc_var(
            ds,
            inp.get("lon_var"),
            ["lon", "longitude", "x", "LON", "XLONG"],
            "longitude",
        )
        lat_var = _smc_pick_nc_var(
            ds,
            inp.get("lat_var"),
            ["lat", "latitude", "y", "LAT", "XLAT"],
            "latitude",
        )
        bathy_var = _smc_pick_nc_var(
            ds,
            inp.get("bathy_var"),
            ["elevation", "z", "depth", "bathymetry", "Bathymetry"],
            "bathymetry",
        )
        lon = np.asarray(ds.variables[lon_var][:], dtype=float).squeeze()
        lat = np.asarray(ds.variables[lat_var][:], dtype=float).squeeze()

    if lon.ndim != 1 or lat.ndim != 1:
        raise ValueError("SMC viz: bathymetry lon/lat must be 1D")
    if bool(inp.get("auto_flip_lat", True)) and lat.size > 1 and float(lat[0]) > float(lat[-1]):
        lat = lat[::-1]
    if bool(inp.get("auto_flip_lon", True)) and lon.size > 1 and float(lon[0]) > float(lon[-1]):
        lon = lon[::-1]
    dlon = float(lon[1] - lon[0]) if lon.size > 1 else 1.0
    dlat = float(lat[1] - lat[0]) if lat.size > 1 else 1.0
    lon0, lat0 = float(lon[0]), float(lat[0])

    root = os.path.abspath(os.path.normpath(grid_dir))
    return {
        "cells_file": os.path.join(root, "grid_cell.dat"),
        "bathymetry_file": bathy_path,
        "lon_var": lon_var,
        "lat_var": lat_var,
        "bathy_var": bathy_var,
        "dlon": dlon,
        "dlat": dlat,
        "lon_origin": lon0,
        "lat_origin": lat0,
        "grid_json": doc,
    }


def smc_run_metadata_path(grid_dir: str) -> str | None:
    """输出目录中的 ``grid.json``（平铺配置或旧版元数据），需同目录存在 ``grid_cell.dat``。

    [EN] The ``grid.json`` in the output directory (flat config or legacy metadata);
    ``grid_cell.dat`` must also exist in the same directory.
    """
    root = os.path.abspath(os.path.normpath(grid_dir))
    cell = os.path.join(root, "grid_cell.dat")
    if not os.path.isfile(cell):
        return None
    for name in ("grid.json", "grid_run_info.json"):
        p = os.path.join(root, name)
        if not os.path.isfile(p):
            continue
        try:
            with open(p, encoding="utf-8") as f:
                doc = json.load(f)
        except Exception:
            continue
        if _is_smc_legacy_run_metadata(doc):
            return p
        if _is_smc_flat_config_doc(doc):
            return p
    return None


def input_fingerprint(grid_dir: str, mode: str) -> dict | None:
    """根据网格类型收集输入文件 mtime/size，用于可视化缓存失效判断。

    [EN] Collect input file mtime/size based on grid type for visualization cache invalidation.
    """
    if mode == "unst":
        p = os.path.join(grid_dir, "grid.ww3")
        fp = _stat_fp(p)
        if fp is None:
            return None
        return {"grid.ww3": fp}
    if mode == "smc":
        cell_p = os.path.join(grid_dir, "grid_cell.dat")
        fp_cell = _stat_fp(cell_p)
        meta_p = smc_run_metadata_path(grid_dir)
        fp_meta = _stat_fp(meta_p) if meta_p else None
        if fp_cell is None or fp_meta is None:
            return None
        return {"grid_cell.dat": fp_cell, os.path.basename(meta_p): fp_meta}
    if mode == "structured":
        out = {}
        desc = _structured_grid_desc_path(grid_dir)
        if not desc:
            return None
        out[os.path.basename(desc)] = _stat_fp(desc)
        for name in ("grid.bot", "grid.obst"):
            p = os.path.join(grid_dir, name)
            fp = _stat_fp(p)
            if fp is None:
                return None
            out[name] = fp
        mask_p = _structured_mask_path(grid_dir)
        if mask_p is None:
            return None
        out["grid.mask"] = _stat_fp(mask_p)
        return out
    return None


def expected_outputs_unst() -> list[str]:
    return ["grid_unst_bathymetry.png", "grid_unst_structure.png"]


def expected_outputs_smc() -> list[str]:
    return ["grid_smc_bathymetry.png", "grid_smc_structure.png"]


def _load_smc_run_info(grid_dir: str) -> dict | None:
    p = smc_run_metadata_path(grid_dir)
    if not p:
        return None
    try:
        with open(p, encoding="utf-8") as f:
            doc = json.load(f)
        if not isinstance(doc, dict):
            return None
        if _is_smc_flat_config_doc(doc) and not _is_smc_legacy_run_metadata(doc):
            return _smc_flat_config_to_run_info(doc, grid_dir)
        return doc
    except Exception:
        return None


def _load_smc_cell_array(path: str) -> tuple[np.ndarray, np.ndarray | None]:
    arr = np.genfromtxt(path, dtype=np.int64, skip_header=1)
    if arr.size == 0:
        raise ValueError("empty SMC cell file")
    if arr.ndim == 1:
        arr = arr.reshape(1, -1)
    if arr.shape[1] < 4:
        raise ValueError("SMC cell rows need at least 4 integer columns")
    core = np.ascontiguousarray(arr[:, :4])
    depth = np.asarray(arr[:, 4], dtype=float) if arr.shape[1] >= 5 else None
    return core, depth


def _smc_zlonlat_dgrid(run_info: dict) -> tuple[float, float, float, float]:
    """Origin and spacing for SMC cell → lon/lat (same convention as smcellmap.smcell)."""
    dlon = float(run_info["dlon"])
    dlat = float(run_info["dlat"])
    gj = run_info.get("grid_json")
    if isinstance(gj, dict):
        wr = gj.get("ww3_rect")
        if isinstance(wr, dict):
            try:
                return float(wr["x0"]), float(wr["y0"]), dlon, dlat
            except (KeyError, TypeError, ValueError):
                pass
        grid = gj.get("grid")
        if isinstance(grid, dict):
            org = grid.get("origin")
            if isinstance(org, dict):
                lon0 = org.get("lon0", org.get("x0lon"))
                lat0 = org.get("lat0", org.get("y0lat"))
                if lon0 is not None and lat0 is not None:
                    try:
                        return float(lon0), float(lat0), dlon, dlat
                    except (TypeError, ValueError):
                        pass
    # Compatibility fallback for legacy run metadata.
    if "lon_origin" in run_info and "lat_origin" in run_info:
        return float(run_info["lon_origin"]), float(run_info["lat_origin"]), dlon, dlat
    path = run_info.get("bathymetry_file") or ""
    if not path or not os.path.isfile(path):
        raise ValueError("SMC metadata missing lon_origin/lat_origin and bathymetry_file")
    import netCDF4 as nc

    lv = run_info.get("lon_var")
    lat_v = run_info.get("lat_var")
    with nc.Dataset(path, "r") as ds:
        lon = np.asarray(ds.variables[str(lv)][:], dtype=float).squeeze()
        lat = np.asarray(ds.variables[str(lat_v)][:], dtype=float).squeeze()
    if lon.ndim != 1 or lat.ndim != 1:
        raise ValueError("SMC viz: bathymetry lon/lat must be 1D")
    if float(lat[0]) > float(lat[-1]):
        lat = lat[::-1]
    if float(lon[0]) > float(lon[-1]):
        lon = lon[::-1]
    return float(lon[0]), float(lat[0]), dlon, dlat


def _smc_sample_bathy_at_centers(run_info: dict, lon_c: np.ndarray, lat_c: np.ndarray) -> np.ndarray:
    path = run_info.get("bathymetry_file") or ""
    if not path or not os.path.isfile(path):
        raise ValueError("missing bathymetry_file in SMC metadata (grid.json)")
    import netCDF4 as nc

    lv = run_info.get("lon_var")
    lat_v = run_info.get("lat_var")
    bv = run_info.get("bathy_var")
    with nc.Dataset(path, "r") as ds:
        lon = np.asarray(ds.variables[str(lv)][:], dtype=float).squeeze()
        lat = np.asarray(ds.variables[str(lat_v)][:], dtype=float).squeeze()
        bathy = np.asarray(ds.variables[str(bv)][:], dtype=float).squeeze()
    if bathy.ndim != 2:
        raise ValueError("bathymetry variable must be 2D after squeeze")
    if lon.ndim != 1 or lat.ndim != 1:
        raise ValueError("1D lon/lat required")
    if float(lat[0]) > float(lat[-1]):
        lat = lat[::-1]
        bathy = bathy[::-1, :]
    if float(lon[0]) > float(lon[-1]):
        lon = lon[::-1]
        bathy = bathy[:, ::-1]
    if bathy.shape == (lon.size, lat.size):
        bathy = bathy.T
    if bathy.shape != (lat.size, lon.size):
        raise ValueError(f"bathy shape {bathy.shape} vs (nlat,nlon)=({lat.size},{lon.size})")
    dlon = float(lon[1] - lon[0]) if lon.size > 1 else float(run_info["dlon"])
    dlat = float(lat[1] - lat[0]) if lat.size > 1 else float(run_info["dlat"])
    ix = np.rint((lon_c - float(lon[0])) / dlon).astype(np.int64)
    iy = np.rint((lat_c - float(lat[0])) / dlat).astype(np.int64)
    ix = np.clip(ix, 0, lon.size - 1)
    iy = np.clip(iy, 0, lat.size - 1)
    return bathy[iy, ix].astype(float)


def _smc_cell_centers(cel: np.ndarray, zlon: float, zlat: float, dlon: float, dlat: float) -> tuple[np.ndarray, np.ndarray]:
    lon_c = zlon + (cel[:, 0].astype(float) + 0.5 * cel[:, 2].astype(float)) * dlon
    lat_c = zlat + (cel[:, 1].astype(float) + 0.5 * cel[:, 3].astype(float)) * dlat
    return lon_c, lat_c


def _smc_regional_bounds_from_run_info(run_info: dict) -> tuple[float, float, float, float] | None:
    """``(west, east, south, north)`` from ``grid_json`` if regional SMC; else ``None``."""
    gj = run_info.get("grid_json")
    if not isinstance(gj, dict):
        return None
    grid = gj.get("grid")
    if not isinstance(grid, dict) or bool(grid.get("global", True)):
        return None
    b = grid.get("regional_bounds")
    if not isinstance(b, dict):
        return None

    def _pickf(*keys: str) -> float | None:
        for k in keys:
            v = b.get(k)
            if v is None:
                continue
            try:
                return float(v)
            except (TypeError, ValueError):
                continue
        return None

    wl = _pickf("west_lon", "lon_min", "xstart", "min_lon")
    el = _pickf("east_lon", "lon_max", "xend", "max_lon")
    sl = _pickf("south_lat", "lat_min", "ystart", "min_lat")
    nl = _pickf("north_lat", "lat_max", "yend", "max_lat")
    if wl is None or el is None or sl is None or nl is None:
        return None
    w, e = (wl, el) if wl <= el else (el, wl)
    s, n = (sl, nl) if sl <= nl else (nl, sl)
    return w, e, s, n


def _smc_extent_for_plot(run_info: dict, lon_c: np.ndarray, lat_c: np.ndarray) -> list[float]:
    """
    区域 SMC 使用用户指定的 ``regional_bounds`` 作为精确视口。生成器可以向外对齐
    单元以完整覆盖计算域，但可视化不应因此额外显示一圈区域。缺少区域范围元数据时，
    才根据实际格心自动计算显示范围。

    [EN] Regional SMC plots use the requested ``regional_bounds`` as the exact viewport.
    Generated cells may align outward to cover the computational domain, but that alignment
    must not enlarge the plotted map. Fall back to cell-derived bounds only when metadata is absent.
    """
    rb = _smc_regional_bounds_from_run_info(run_info)
    if rb is not None:
        return list(rb)
    if lon_c.size == 0:
        return [-180.0, 180.0, -90.0, 90.0]
    return unst_extent_from_xy(np.column_stack([lon_c, lat_c]))


def _smc_unique_rect_outline_segments(
    cel: np.ndarray,
    zlon: float,
    zlat: float,
    dlon: float,
    dlat: float,
) -> np.ndarray:
    """
    Undirected unique edges of the union of SMC axis-aligned rectangles. Shared edges
    between adjacent cells appear once, so the outline is spatially continuous (unlike
    random subsampling of whole rectangles, which leaves holes).
    Returns an array of shape ``(M, 2, 2)`` as segments for ``LineCollection``.
    """
    n = int(cel.shape[0])
    if n == 0:
        return np.zeros((0, 2, 2), dtype=np.float64)
    di = cel[:, 2].astype(np.float64) * dlon
    dj = cel[:, 3].astype(np.float64) * dlat
    x0 = zlon + cel[:, 0].astype(np.float64) * dlon
    y0 = zlat + cel[:, 1].astype(np.float64) * dlat
    x1 = x0 + di
    y1 = y0 + dj
    s = np.empty((4 * n, 2, 2), dtype=np.float64)
    s[0::4, 0, 0] = x0
    s[0::4, 0, 1] = y0
    s[0::4, 1, 0] = x1
    s[0::4, 1, 1] = y0
    s[1::4, 0, 0] = x1
    s[1::4, 0, 1] = y0
    s[1::4, 1, 0] = x1
    s[1::4, 1, 1] = y1
    s[2::4, 0, 0] = x1
    s[2::4, 0, 1] = y1
    s[2::4, 1, 0] = x0
    s[2::4, 1, 1] = y1
    s[3::4, 0, 0] = x0
    s[3::4, 0, 1] = y1
    s[3::4, 1, 0] = x0
    s[3::4, 1, 1] = y0
    dec = 6
    p0 = np.round(s[:, 0, :], dec)
    p1 = np.round(s[:, 1, :], dec)
    swap = (p1[:, 0] < p0[:, 0]) | ((p1[:, 0] == p0[:, 0]) & (p1[:, 1] < p0[:, 1]))
    lo = np.where(swap[:, None], p1, p0)
    hi = np.where(swap[:, None], p0, p1)
    keys = np.ascontiguousarray(np.hstack([lo, hi]))
    _, idx = np.unique(keys, axis=0, return_index=True)
    idx.sort()
    return np.stack([lo[idx], hi[idx]], axis=1)


# 水深图：按格块多边形填色，过大时抽样（避免内存/渲染过久）
# [EN] Bathymetry plot: fill by cell polygon; subsample when too large (to avoid excessive memory/rendering time)
SMC_VIZ_BATHY_MAX_CELLS = 450_000
# 结构图：对「格块」上限，超过则按索引步长稀疏化再做去重边（极少数特大海域网格）
# [EN] Structure plot: cap on "cells"; when exceeded, sparsify by index stride before deduplicating edges (very rare, extremely large ocean grids)
SMC_VIZ_STRUCT_MAX_CELLS = 2_500_000


def _smc_cell_rect_vertices(cel: np.ndarray, zlon: float, zlat: float, dlon: float, dlat: float) -> np.ndarray:
    """Each SMC cell as 4 CCW lon/lat corners, shape ``(n, 4, 2)``."""
    n = int(cel.shape[0])
    if n == 0:
        return np.zeros((0, 4, 2), dtype=np.float64)
    i0 = cel[:, 0].astype(np.float64)
    j0 = cel[:, 1].astype(np.float64)
    di = cel[:, 2].astype(np.float64) * dlon
    dj = cel[:, 3].astype(np.float64) * dlat
    x0 = zlon + i0 * dlon
    y0 = zlat + j0 * dlat
    x1 = x0 + di
    y1 = y0 + dj
    out = np.empty((n, 4, 2), dtype=np.float64)
    out[:, 0, 0] = x0
    out[:, 0, 1] = y0
    out[:, 1, 0] = x1
    out[:, 1, 1] = y0
    out[:, 2, 0] = x1
    out[:, 2, 1] = y1
    out[:, 3, 0] = x0
    out[:, 3, 1] = y1
    return out


def run_smc(grid_dir: str) -> dict:
    """读取 SMC ``grid_cell.dat`` 与 ``grid.json`` 元数据，生成格块水深与边界结构图。

    [EN] Read SMC ``grid_cell.dat`` and ``grid.json`` metadata, and generate cell bathymetry and boundary structure plots.
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    _configure_matplotlib_cjk_fonts()
    from matplotlib.collections import LineCollection
    import cartopy.crs as ccrs
    import cartopy.feature as cfeature

    photo_dir = os.path.join(grid_dir, "photo", "grid")
    os.makedirs(photo_dir, exist_ok=True)
    fp_now = input_fingerprint(grid_dir, "smc")
    outs = expected_outputs_smc()
    if fp_now and cache_is_current(grid_dir, "smc"):
        imgs = cached_image_paths(grid_dir, "smc")
        return {"ok": True, "skipped": True, "images": imgs, "photo_dir": photo_dir}

    ri = _load_smc_run_info(grid_dir)
    if not ri:
        return {"ok": False, "error": "missing SMC run metadata (grid.json)", "images": [], "photo_dir": photo_dir}
    cell_path = os.path.join(grid_dir, "grid_cell.dat")
    if not os.path.isfile(cell_path):
        return {"ok": False, "error": "missing grid_cell.dat", "images": [], "photo_dir": photo_dir}

    emit_log(_viz_tr("step1_grid_viz_worker_read", "🔄 正在读取网格数据…"))
    try:
        cel, depth_file = _load_smc_cell_array(cell_path)
        zlon, zlat, dlon, dlat = _smc_zlonlat_dgrid(ri)
        lon_c, lat_c = _smc_cell_centers(cel, zlon, zlat, dlon, dlat)
        if depth_file is not None:
            depth = depth_file
        else:
            depth = _smc_sample_bathy_at_centers(ri, lon_c, lat_c)
    except Exception as e:
        return {"ok": False, "error": f"SMC read: {e}", "images": [], "photo_dir": photo_dir}

    extent = _smc_extent_for_plot(ri, lon_c, lat_c)
    fig_wh = unst_figsize_for_extent(extent)

    nc = int(cel.shape[0])
    cel_b = cel
    depth_b = np.asarray(depth, dtype=float)
    if nc > SMC_VIZ_BATHY_MAX_CELLS:
        stride = int(np.ceil(nc / SMC_VIZ_BATHY_MAX_CELLS))
        cel_b = cel[::stride]
        depth_b = depth_b[::stride]
        emit_log(
            _viz_tr(
                "step1_grid_viz_smc_bathy_subsample",
                "   SMC 格块过多（>{max}），水深图已按步长 {stride} 抽样填色。",
            ).format(max=SMC_VIZ_BATHY_MAX_CELLS, stride=stride)
        )

    out_bathy = os.path.join(photo_dir, outs[0])
    emit_log(_viz_tr("step1_grid_viz_worker_plot_bathy", "🔄 正在绘制水深图…"))
    try:
        fig = plt.figure(figsize=fig_wh)
        ax = fig.add_subplot(1, 1, 1, projection=ccrs.PlateCarree(central_longitude=0.5 * (extent[0] + extent[1])))
        ax.set_extent(extent, crs=ccrs.PlateCarree())
        try:
            ax.add_feature(cfeature.COASTLINE, linewidth=0.4, zorder=5)
        except Exception:
            pass
        d_all = np.asarray(depth, dtype=float)
        vmin, vmax = float(np.nanmin(d_all)), float(np.nanmax(d_all))
        if not np.isfinite(vmin) or not np.isfinite(vmax) or vmin == vmax:
            vmax = vmin + 1.0 if np.isfinite(vmin) else 1.0
            vmin = vmin if np.isfinite(vmin) else 0.0
        from matplotlib.collections import PolyCollection
        import matplotlib.colors as mcolors

        polys = _smc_cell_rect_vertices(cel_b, zlon, zlat, dlon, dlat)
        norm = mcolors.Normalize(vmin=vmin, vmax=vmax)
        pc = PolyCollection(
            polys,
            array=np.asarray(depth_b, dtype=float),
            cmap="jet",
            norm=norm,
            edgecolors="none",
            linewidths=0,
            antialiaseds=False,
            transform=ccrs.PlateCarree(),
            zorder=1,
        )
        ax.add_collection(pc)
        plt.colorbar(pc, ax=ax, shrink=0.7).set_label(
            _viz_tr("step1_grid_viz_smc_colorbar", "地形高程（m）"),
            fontsize=10,
        )
        ax.set_title(_viz_tr("step1_grid_viz_smc_bathy_title", "SMC 网格 — 水深（格块填色）"), fontsize=13)
        plt.tight_layout()
        plt.savefig(out_bathy, dpi=OUTPUT_DPI, bbox_inches="tight")
        plt.close(fig)
    except Exception as e:
        plt.close("all")
        return {"ok": False, "error": f"SMC bathy plot: {e}", "images": [], "photo_dir": photo_dir}

    emit_log(_viz_tr("step1_grid_viz_worker_plot_struct", "🔄 正在绘制网格结构图…"))
    out_struct = os.path.join(photo_dir, outs[1])
    try:
        nrect = int(cel.shape[0])
        cel_plot = cel
        if nrect > SMC_VIZ_STRUCT_MAX_CELLS:
            stride = int(np.ceil(nrect / SMC_VIZ_STRUCT_MAX_CELLS))
            cel_plot = cel[::stride]
            emit_log(
                _viz_tr(
                    "step1_grid_viz_smc_struct_subsample",
                    "   SMC 格块过多（>{max}），已按步长 {stride} 抽样后再画边界（仅超大网格）。",
                ).format(max=SMC_VIZ_STRUCT_MAX_CELLS, stride=stride)
            )
        segs_arr = _smc_unique_rect_outline_segments(cel_plot, zlon, zlat, dlon, dlat)
        fig = plt.figure(figsize=fig_wh)
        ax = fig.add_subplot(1, 1, 1, projection=ccrs.PlateCarree(central_longitude=0.5 * (extent[0] + extent[1])))
        ax.set_extent(extent, crs=ccrs.PlateCarree())
        try:
            ax.add_feature(cfeature.COASTLINE, linewidth=0.4, zorder=5)
        except Exception:
            pass
        lw = max(0.12, 0.12 * (OUTPUT_DPI / 150.0))
        if segs_arr.shape[0] > 0:
            lc = LineCollection(
                segs_arr,
                colors="k",
                linewidths=lw,
                antialiaseds=True,
                transform=ccrs.PlateCarree(),
            )
            ax.add_collection(lc)
        ax.set_title(_viz_tr("step1_grid_viz_smc_struct_title", "SMC 网格 — 结构（格块边界）"), fontsize=13)
        plt.tight_layout()
        plt.savefig(out_struct, dpi=OUTPUT_DPI, bbox_inches="tight")
        plt.close(fig)
    except Exception as e:
        plt.close("all")
        return {"ok": False, "error": f"SMC structure plot: {e}", "images": [], "photo_dir": photo_dir}

    _save_cache(photo_dir, "smc", fp_now, outs)
    return {
        "ok": True,
        "skipped": False,
        "images": [os.path.join(photo_dir, n) for n in outs],
        "photo_dir": photo_dir,
    }


def cache_is_current(grid_dir: str, mode: str) -> bool:
    """检查 ``.grid_viz_cache.json`` 是否与当前输入指纹一致且输出 PNG 均存在。

    [EN] Check whether ``.grid_viz_cache.json`` matches the current input fingerprint and all output PNGs exist.
    """
    photo_dir = os.path.join(grid_dir, "photo", "grid")
    fp_now = input_fingerprint(grid_dir, mode)
    if fp_now is None:
        return False
    cpath = os.path.join(photo_dir, CACHE_FILE)
    if not os.path.isfile(cpath):
        return False
    try:
        with open(cpath, "r", encoding="utf-8") as f:
            doc = json.load(f)
    except Exception:
        return False
    if doc.get("version") != CACHE_VERSION or doc.get("mode") != mode:
        return False
    if doc.get("fingerprint") != fp_now:
        return False
    outputs = doc.get("outputs")
    if not isinstance(outputs, list) or not outputs:
        return False
    for name in outputs:
        if not os.path.isfile(os.path.join(photo_dir, name)):
            return False
    return True


def cached_image_paths(grid_dir: str, mode: str) -> list[str]:
    photo_dir = os.path.join(grid_dir, "photo", "grid")
    cpath = os.path.join(photo_dir, CACHE_FILE)
    try:
        with open(cpath, "r", encoding="utf-8") as f:
            doc = json.load(f)
    except Exception:
        return []
    if doc.get("mode") != mode:
        return []
    return [os.path.join(photo_dir, n) for n in doc.get("outputs", [])]


def _save_cache(photo_dir: str, mode: str, fingerprint: dict, outputs: list[str]) -> None:
    os.makedirs(photo_dir, exist_ok=True)
    doc = {"version": CACHE_VERSION, "mode": mode, "fingerprint": fingerprint, "outputs": outputs}
    with open(os.path.join(photo_dir, CACHE_FILE), "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2, ensure_ascii=False)


# --- Gmsh / unst ---


def read_gmsh_ww3(filename: str):
    with open(filename, "r", encoding="utf-8", errors="ignore") as f:
        for _ in range(4):
            next(f)
        nn = int(next(f).strip())
        xy = np.zeros((nn, 2), dtype=np.double)
        depth = np.zeros(nn, dtype=np.double)
        for _i in range(nn):
            line = next(f).split()
            idx = int(line[0]) - 1
            x_coord = float(line[1])
            xy[idx, 0] = x_coord - 360 if x_coord > 180 else x_coord
            xy[idx, 1] = float(line[2])
            depth[idx] = float(line[3])
        next(f)
        next(f)
        ne = int(next(f).strip())
        ecttemp = np.zeros((ne, 3), dtype=np.int32)
        elem_count = 0
        for _ in range(ne):
            line = next(f).split()
            eltype = int(line[1])
            ntags = int(line[2])
            i0 = 3 + ntags
            if eltype == 15:
                continue
            if len(line) >= i0 + 3:
                ecttemp[elem_count, :] = [
                    int(line[i0]) - 1,
                    int(line[i0 + 1]) - 1,
                    int(line[i0 + 2]) - 1,
                ]
                elem_count += 1
        ect = ecttemp[:elem_count, :]
    return xy, depth, ect


def unst_extent_from_xy(xy, margin_deg=None):
    lon_min = float(np.min(xy[:, 0]))
    lon_max = float(np.max(xy[:, 0]))
    lat_min = float(np.min(xy[:, 1]))
    lat_max = float(np.max(xy[:, 1]))
    lon_s = max(lon_max - lon_min, 1e-9)
    lat_s = max(lat_max - lat_min, 1e-9)
    m = max(0.02 * max(lon_s, lat_s), 0.1) if margin_deg is None else float(margin_deg)
    return [lon_min - m, lon_max + m, max(-90.0, lat_min - m), min(90.0, lat_max + m)]


def unst_figsize_for_extent(extent, base_area=160.0, w_clip=(6.0, 28.0), h_clip=(4.5, 20.0)):
    """
    Match figure width/height to the map box so PlateCarree regional plots are not
    letterboxed with large white margins (common for long thin domains).
    base_area is target w*h in inch^2 (default ~ same as 16x10).
    """
    lon0, lon1, lat0, lat1 = extent
    lon_sp = max(lon1 - lon0, 1e-6)
    lat_sp = max(lat1 - lat0, 1e-6)
    mid_lat = 0.5 * (lat0 + lat1)
    cos_lat = max(abs(np.cos(np.radians(mid_lat))), 0.12)
    # Rough km aspect: E–W vs N–S at mid-latitude
    data_w_over_h = (lon_sp * cos_lat) / lat_sp
    w = float(np.sqrt(max(base_area * data_w_over_h, 1e-6)))
    h = float(np.sqrt(max(base_area / data_w_over_h, 1e-6)))
    w = float(np.clip(w, w_clip[0], w_clip[1]))
    h = float(np.clip(h, h_clip[0], h_clip[1]))
    return (w, h)


def unst_triangulation_mask(xy, ect):
    x_coords = xy[ect, 0]
    signs = np.sign(x_coords)
    uniform_sign = np.ptp(signs, axis=1) == 0
    near_dateline = (np.abs(x_coords) < 10).any(axis=1)
    return ~(uniform_sign | near_dateline)


def unst_wireframe_segments(
    xy: np.ndarray,
    ect: np.ndarray,
    tri_mpl_mask: np.ndarray | None,
    max_edges: int,
) -> tuple[np.ndarray, int]:
    """
    从有效三角形提取无向唯一边，得到 LineCollection 用的线段数组 (n_seg, 2, 2)[lonlat]。
    tri_mpl_mask 与 Matplotlib Triangulation.mask 一致：True 表示该三角形不绘制。
    返回 (segments, n_unique_edges_before_cap)。

    [EN] Extract undirected unique edges from valid triangles, producing a segment array
    (n_seg, 2, 2)[lonlat] for LineCollection.
    tri_mpl_mask is consistent with Matplotlib Triangulation.mask: True means the triangle is not drawn.
    Returns (segments, n_unique_edges_before_cap).
    """
    ntri = int(ect.shape[0])
    if ntri == 0:
        return np.zeros((0, 2, 2), dtype=np.double), 0
    if tri_mpl_mask is not None and len(tri_mpl_mask) == ntri:
        valid = ~np.asarray(tri_mpl_mask, dtype=bool)
    else:
        valid = np.ones(ntri, dtype=bool)
    if not np.any(valid):
        valid = np.ones(ntri, dtype=bool)
    ev = ect[valid]
    e = np.concatenate([ev[:, [0, 1]], ev[:, [1, 2]], ev[:, [2, 0]]], axis=0)
    lo = np.minimum(e[:, 0], e[:, 1])
    hi = np.maximum(e[:, 0], e[:, 1])
    pairs = np.unique(np.column_stack([lo, hi]), axis=0)
    n_unique = int(pairs.shape[0])
    if n_unique > max_edges:
        rng = np.random.default_rng(42)
        sel = rng.choice(n_unique, size=max_edges, replace=False)
        pairs = pairs[sel]
    segs = np.stack([xy[pairs[:, 0]], xy[pairs[:, 1]]], axis=1).astype(np.double, copy=False)
    return segs, n_unique


# --- Structured WW3 ASCII ---


_rgd_parse = None


def _rect_grid_desc_module():
    global _rgd_parse
    if _rgd_parse is None:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rect_grid_desc_parse.py")
        spec = importlib.util.spec_from_file_location("_rect_grid_desc_parse", path)
        if spec is None or spec.loader is None:
            raise ImportError(path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _rgd_parse = mod
    return _rgd_parse


def read_ww3meta(fname: str):
    """Structured grid: MATLAB-style ``grid.nml`` (&RECT_NML) or legacy ASCII."""
    try:
        lon, lat = _rect_grid_desc_module().structured_lon_lat_mesh(fname)
        if lon is None:
            return None, None
        return lon, lat
    except Exception:
        return None, None


def read_ww3file(fname: str, Nx: int, Ny: int):
    try:
        data = []
        with open(fname, "r", encoding="utf-8", errors="ignore") as fid:
            for line in fid:
                values = [int(x) for x in line.split()]
                if values:
                    data.append(values)
        arr = np.array(data[:Ny])
        return arr
    except Exception:
        return None


def read_ww3obstr(fname: str, Nx: int, Ny: int):
    try:
        data = []
        with open(fname, "r", encoding="utf-8", errors="ignore") as fid:
            for line in fid:
                line = line.strip()
                if line:
                    values = [int(x) for x in line.split()]
                    if values:
                        data.append(values)
        if len(data) < Ny * 2:
            return None, None
        sx_data = np.array(data[:Ny])
        sy_start = Ny
        while sy_start < len(data) and len(data[sy_start]) == 0:
            sy_start += 1
        if sy_start + Ny > len(data):
            return None, None
        sy_data = np.array(data[sy_start : sy_start + Ny])
        if sx_data.shape[1] != Nx or sy_data.shape[1] != Nx:
            return None, None
        return sx_data, sy_data
    except Exception:
        return None, None


def _plot_pcolormesh_file(lon, lat, data, title, output_path, cmap="jet", shading="flat", figsize=None):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import cartopy.crs as ccrs
    import cartopy.feature as cfeature

    xy_flat = np.column_stack([np.asarray(lon, dtype=float).ravel(), np.asarray(lat, dtype=float).ravel()])
    ext = unst_extent_from_xy(xy_flat)
    if figsize is None:
        figsize = unst_figsize_for_extent(ext)
    fig = plt.figure(figsize=figsize)
    ax = fig.add_subplot(1, 1, 1, projection=ccrs.PlateCarree())
    ax.set_extent(ext, crs=ccrs.PlateCarree())
    try:
        ax.add_feature(cfeature.COASTLINE, linewidth=0.4, zorder=5)
    except Exception:
        pass
    vmin = float(np.nanmin(data))
    vmax = float(np.nanmax(data))
    if vmin == vmax:
        vmax = vmin + 1.0
    if shading in ("interp", "gouraud"):
        im = ax.pcolormesh(
            lon,
            lat,
            data,
            cmap=cmap,
            vmin=vmin,
            vmax=vmax,
            shading="gouraud",
            transform=ccrs.PlateCarree(),
        )
    else:
        Ny, Nx = data.shape
        if Nx > 1:
            dx = (lon[0, -1] - lon[0, 0]) / (Nx - 1)
            lon_edges = np.linspace(lon[0, 0] - dx / 2, lon[0, -1] + dx / 2, Nx + 1)
        else:
            lon_edges = np.array([lon[0, 0] - 0.025, lon[0, 0] + 0.025])
        if Ny > 1:
            dy = (lat[-1, 0] - lat[0, 0]) / (Ny - 1)
            lat_edges = np.linspace(lat[0, 0] - dy / 2, lat[-1, 0] + dy / 2, Ny + 1)
        else:
            lat_edges = np.array([lat[0, 0] - 0.025, lat[0, 0] + 0.025])
        lon_grid, lat_grid = np.meshgrid(lon_edges, lat_edges)
        im = ax.pcolormesh(
            lon_grid,
            lat_grid,
            data,
            cmap=cmap,
            vmin=vmin,
            vmax=vmax,
            shading="flat",
            transform=ccrs.PlateCarree(),
        )
    ax.set_title(title, fontsize=14, fontweight="bold")
    plt.colorbar(im, ax=ax, shrink=0.7).set_label(title, fontsize=10)
    plt.tight_layout()
    plt.savefig(output_path, dpi=OUTPUT_DPI, bbox_inches="tight")
    plt.close(fig)


def plot_structured_grid_structure(lon: np.ndarray, lat: np.ndarray, output_path: str) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import cartopy.crs as ccrs
    import cartopy.feature as cfeature

    Ny, Nx = lon.shape
    xy_flat = np.column_stack([lon.ravel(), lat.ravel()])
    ext = unst_extent_from_xy(xy_flat)
    figsize = unst_figsize_for_extent(ext)
    fig = plt.figure(figsize=figsize)
    ax = fig.add_subplot(1, 1, 1, projection=ccrs.PlateCarree())
    ax.set_extent(ext, crs=ccrs.PlateCarree())
    try:
        ax.add_feature(cfeature.COASTLINE, linewidth=0.4, zorder=5)
    except Exception:
        pass
    step = max(1, int(np.ceil(max(Nx, Ny) / STRUCTURED_MAX_LINES)))
    lw = max(0.15, 0.12 * (OUTPUT_DPI / 150.0))
    pc = ccrs.PlateCarree()
    for j in range(0, Nx, step):
        ax.plot(lon[:, j], lat[:, j], "k-", linewidth=lw, transform=pc)
    for i in range(0, Ny, step):
        ax.plot(lon[i, :], lat[i, :], "k-", linewidth=lw, transform=pc)
    ax.set_title("Structured grid — layout", fontsize=14, fontweight="bold")
    plt.tight_layout()
    plt.savefig(output_path, dpi=OUTPUT_DPI, bbox_inches="tight")
    plt.close(fig)


def run_unst(grid_dir: str) -> dict:
    """读取 ``grid.ww3``（Gmsh 格式）并生成非结构网格水深图与结构线图。

    [EN] Read ``grid.ww3`` (Gmsh format) and generate unstructured grid bathymetry and structure wireframe plots.
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.tri as mtri
    from matplotlib.collections import LineCollection
    import cartopy.crs as ccrs
    import cartopy.feature as cfeature

    ww3_path = os.path.join(grid_dir, "grid.ww3")
    photo_dir = os.path.join(grid_dir, "photo", "grid")
    os.makedirs(photo_dir, exist_ok=True)
    fp_now = input_fingerprint(grid_dir, "unst")
    outs = expected_outputs_unst()
    if fp_now and cache_is_current(grid_dir, "unst"):
        imgs = cached_image_paths(grid_dir, "unst")
        return {"ok": True, "skipped": True, "images": imgs, "photo_dir": photo_dir}
    emit_log(_viz_tr("step1_grid_viz_worker_read", "🔄 正在读取网格数据…"))
    try:
        xy, depth, ect = read_gmsh_ww3(ww3_path)
    except Exception as e:
        return {"ok": False, "error": f"read grid.ww3: {e}", "images": [], "photo_dir": photo_dir}
    if ect.size == 0:
        return {"ok": False, "error": "no triangles in grid.ww3", "images": [], "photo_dir": photo_dir}
    tri_mask = unst_triangulation_mask(xy, ect)
    triang = mtri.Triangulation(xy[:, 0], xy[:, 1], triangles=ect, mask=tri_mask)
    extent = unst_extent_from_xy(xy)
    fig_wh = unst_figsize_for_extent(extent)

    out_bathy = os.path.join(photo_dir, outs[0])
    emit_log(_viz_tr("step1_grid_viz_worker_plot_bathy", "🔄 正在绘制水深图…"))
    try:
        fig = plt.figure(figsize=fig_wh)
        ax = fig.add_subplot(1, 1, 1, projection=ccrs.PlateCarree(central_longitude=0.5 * (extent[0] + extent[1])))
        ax.set_extent(extent, crs=ccrs.PlateCarree())
        try:
            ax.add_feature(cfeature.COASTLINE, linewidth=0.4, zorder=5)
        except Exception:
            pass
        d = np.asarray(depth, dtype=float)
        vmin, vmax = float(np.nanmin(d)), float(np.nanmax(d))
        if not np.isfinite(vmin) or not np.isfinite(vmax) or vmin == vmax:
            vmax = vmin + 1.0 if np.isfinite(vmin) else 1.0
            vmin = vmin if np.isfinite(vmin) else 0.0
        # gouraud 着色的 TriMesh 不会被 cartopy 按 transform 重投影（中央经线≠0 时会整体错位到画面外、
        # 导致水深图空白）。先把三角网节点投影到该轴的投影坐标，再以默认 transData 绘制。
        # [EN] Gouraud-shaded TriMesh is not reprojected by cartopy according to transform
        # (when central_longitude ≠ 0 it shifts completely out of the canvas, leaving a blank bathy plot).
        # Project triangulation nodes to the axis projection coordinates first, then draw with default transData.
        _pts = ax.projection.transform_points(ccrs.PlateCarree(), xy[:, 0], xy[:, 1])
        triang_proj = mtri.Triangulation(_pts[:, 0], _pts[:, 1], triangles=ect, mask=tri_mask)
        tpc = ax.tripcolor(
            triang_proj,
            d,
            shading="gouraud",
            cmap="jet",
            vmin=vmin,
            vmax=vmax,
        )
        plt.colorbar(tpc, ax=ax, shrink=0.7).set_label("Depth (m)", fontsize=10)
        ax.set_title("Unstructured mesh — bathymetry", fontsize=13)
        plt.tight_layout()
        plt.savefig(out_bathy, dpi=OUTPUT_DPI, bbox_inches="tight")
        plt.close(fig)
    except Exception as e:
        plt.close("all")
        return {"ok": False, "error": f"bathy plot: {e}", "images": [], "photo_dir": photo_dir}

    out_struct = os.path.join(photo_dir, outs[1])
    emit_log(_viz_tr("step1_grid_viz_worker_plot_struct", "🔄 正在绘制网格结构图…"))
    try:
        segs, _ = unst_wireframe_segments(xy, ect, tri_mask, STRUCTURE_MAX_EDGES)
        fig = plt.figure(figsize=fig_wh)
        ax = fig.add_subplot(1, 1, 1, projection=ccrs.PlateCarree(central_longitude=0.5 * (extent[0] + extent[1])))
        ax.set_extent(extent, crs=ccrs.PlateCarree())
        try:
            ax.add_feature(cfeature.COASTLINE, linewidth=0.4, zorder=5)
        except Exception:
            pass
        tri_lw = max(0.15, 0.12 * (OUTPUT_DPI / 150.0))
        if segs.shape[0] > 0:
            lc = LineCollection(
                segs,
                colors="k",
                linewidths=tri_lw,
                antialiaseds=True,
                transform=ccrs.PlateCarree(),
            )
            ax.add_collection(lc)
        ax.set_title("Unstructured mesh — structure", fontsize=13)
        plt.tight_layout()
        plt.savefig(out_struct, dpi=OUTPUT_DPI, bbox_inches="tight")
        plt.close(fig)
    except Exception as e:
        plt.close("all")
        return {"ok": False, "error": f"structure plot: {e}", "images": [], "photo_dir": photo_dir}

    _save_cache(photo_dir, "unst", fp_now, outs)
    return {
        "ok": True,
        "skipped": False,
        "images": [os.path.join(photo_dir, n) for n in outs],
        "photo_dir": photo_dir,
    }


def run_structured(grid_dir: str) -> dict:
    """读取 structured 网格 bot/mask/obst 与描述文件，生成水深/结构/掩膜/阻障图。

    [EN] Read structured grid bot/mask/obst and description files, and generate bathymetry/structure/mask/obstruction plots.
    """
    photo_dir = os.path.join(grid_dir, "photo", "grid")
    os.makedirs(photo_dir, exist_ok=True)
    fp_now = input_fingerprint(grid_dir, "structured")
    if fp_now and cache_is_current(grid_dir, "structured"):
        imgs = cached_image_paths(grid_dir, "structured")
        return {"ok": True, "skipped": True, "images": imgs, "photo_dir": photo_dir}
    emit_log(_viz_tr("step1_grid_viz_worker_read", "🔄 正在读取网格数据…"))
    mask_p = _structured_mask_path(grid_dir)
    desc_p = _structured_grid_desc_path(grid_dir)
    gf = {
        "meta": desc_p,
        "bot": os.path.join(grid_dir, "grid.bot"),
        "mask": mask_p,
        "obst": os.path.join(grid_dir, "grid.obst"),
    }
    for k, p in gf.items():
        if p is None or not os.path.isfile(p):
            return {"ok": False, "error": f"missing {k}", "images": [], "photo_dir": photo_dir}
    lon, lat = read_ww3meta(gf["meta"])
    if lon is None:
        return {"ok": False, "error": "structured grid description RECT read failed", "images": [], "photo_dir": photo_dir}
    Ny, Nx = lon.shape
    mask = read_ww3file(gf["mask"], Nx, Ny)
    loc = (mask == 0) if mask is not None else None
    depth = read_ww3file(gf["bot"], Nx, Ny)
    if depth is None:
        return {"ok": False, "error": "grid.bot read failed", "images": [], "photo_dir": photo_dir}
    depth = depth.astype(float) / 1000.0
    if loc is not None and depth.shape == loc.shape:
        depth = depth.copy()
        depth[loc] = np.nan
    written: list[str] = []
    emit_log(_viz_tr("step1_grid_viz_worker_plot_bathy", "🔄 正在绘制水深图…"))
    try:
        p_bathy = os.path.join(photo_dir, "grid_bathymetry.png")
        _plot_pcolormesh_file(lon, lat, depth, "Bathymetry", p_bathy, shading="gouraud")
        written.append("grid_bathymetry.png")
    except Exception as e:
        return {"ok": False, "error": f"bathy: {e}", "images": [], "photo_dir": photo_dir}
    emit_log(_viz_tr("step1_grid_viz_worker_plot_struct", "🔄 正在绘制网格结构图…"))
    try:
        p_struct = os.path.join(photo_dir, "grid_structure.png")
        plot_structured_grid_structure(lon, lat, p_struct)
        written.append("grid_structure.png")
    except Exception as e:
        return {"ok": False, "error": f"structure: {e}", "images": [], "photo_dir": photo_dir}
    if mask is not None:
        try:
            p_mask = os.path.join(photo_dir, "grid_mask.png")
            _plot_pcolormesh_file(lon, lat, mask, "Land–sea mask", p_mask, shading="flat")
            written.append("grid_mask.png")
        except Exception as e:
            return {"ok": False, "error": f"mask: {e}", "images": [], "photo_dir": photo_dir}
    sx, sy = read_ww3obstr(gf["obst"], Nx, Ny)
    if sx is not None and sy is not None:
        sx = sx.astype(float) / 100.0
        sy = sy.astype(float) / 100.0
        if loc is not None and sx.shape == loc.shape:
            sx = sx.copy()
            sy = sy.copy()
            sx[loc] = np.nan
            sy[loc] = np.nan
        try:
            _plot_pcolormesh_file(
                lon, lat, sx, "Sx obstruction", os.path.join(photo_dir, "grid_obstruction_x.png"), shading="flat"
            )
            _plot_pcolormesh_file(
                lon, lat, sy, "Sy obstruction", os.path.join(photo_dir, "grid_obstruction_y.png"), shading="flat"
            )
            written.extend(["grid_obstruction_x.png", "grid_obstruction_y.png"])
        except Exception as e:
            return {"ok": False, "error": f"obst: {e}", "images": [], "photo_dir": photo_dir}
    _save_cache(photo_dir, "structured", fp_now, written)
    return {
        "ok": True,
        "skipped": False,
        "images": [os.path.join(photo_dir, n) for n in written],
        "photo_dir": photo_dir,
    }


def main():
    """CLI 入口：解析 ``--mode`` 与 ``--grid-dir``，执行对应可视化并输出协议结果。

    [EN] CLI entry point: parse ``--mode`` and ``--grid-dir``, execute the corresponding visualization, and output protocol results.
    """
    _ensure_worker_language()
    p = argparse.ArgumentParser(description="WW3Tool grid visualization worker")
    p.add_argument("--mode", choices=("unst", "structured", "smc"), required=True)
    p.add_argument("--grid-dir", required=True)
    args = p.parse_args()
    grid_dir = os.path.abspath(os.path.normpath(args.grid_dir))
    if args.mode == "unst":
        res = run_unst(grid_dir)
    elif args.mode == "smc":
        res = run_smc(grid_dir)
    else:
        res = run_structured(grid_dir)
    if not res.get("ok"):
        emit_log(res.get("error", "failed"))
    emit_result(res)
    sys.exit(0 if res.get("ok") else 1)


if __name__ == "__main__":
    main()
