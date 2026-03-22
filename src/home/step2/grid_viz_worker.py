#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
网格可视化子进程：非结构 grid.ww3（Gmsh）与结构化 grid.meta/bot/mask/obst。
生成图片到 <grid_dir>/photo/grid/，并写入 .grid_viz_cache.json 供主进程跳过未改网格。
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np

CACHE_FILE = ".grid_viz_cache.json"
CACHE_VERSION = 4
VIZ_PREFIX = "WW3TOOL_VIZ"


def _ensure_worker_language() -> None:
    try:
        from setting.config import load_config
        from setting.language_manager import load_language

        load_language(load_config().get("LANGUAGE") or "zh_CN")
    except Exception:
        pass


def _viz_tr(key: str, default: str) -> str:
    try:
        from setting.language_manager import tr

        return tr(key, default)
    except Exception:
        return default
# 结构线框：按「边」抽样而非按「三角形」抽样，避免随机抽三角形导致邻边缺失、看起来像碎块。
STRUCTURE_MAX_EDGES = 800_000
STRUCTURED_MAX_LINES = 400
# 导出 PNG 分辨率（提高 DPI 与画布尺寸以改善抽屉/放大查看时的清晰度）
OUTPUT_DPI = 300
FIGSIZE_RECT = (14.0, 9.5)
FIGSIZE_UNST = (16.0, 10.0)


def emit_log(msg: str) -> None:
    print(f"{VIZ_PREFIX}\tLOG\t{msg}", flush=True)


def emit_result(obj: dict) -> None:
    print(f"{VIZ_PREFIX}\tRESULT\t{json.dumps(obj, ensure_ascii=False)}", flush=True)


def _stat_fp(path: str) -> dict | None:
    if not os.path.isfile(path):
        return None
    st = os.stat(path)
    return {"mtime_ns": st.st_mtime_ns, "size": st.st_size}


def input_fingerprint(grid_dir: str, mode: str) -> dict | None:
    if mode == "unst":
        p = os.path.join(grid_dir, "grid.ww3")
        fp = _stat_fp(p)
        if fp is None:
            return None
        return {"grid.ww3": fp}
    if mode == "structured":
        out = {}
        for name in ("grid.meta", "grid.bot", "grid.mask", "grid.obst"):
            p = os.path.join(grid_dir, name)
            fp = _stat_fp(p)
            if fp is None:
                return None
            out[name] = fp
        return out
    return None


def expected_outputs_unst() -> list[str]:
    return ["grid_unst_bathymetry.png", "grid_unst_structure.png"]


def cache_is_current(grid_dir: str, mode: str) -> bool:
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


def read_ww3meta(fname: str):
    try:
        with open(fname, "r", encoding="utf-8", errors="ignore") as fid:
            lines = fid.readlines()
        grid_line_idx = None
        gtype = None
        for i, line in enumerate(lines):
            stripped = line.strip()
            if not stripped or stripped.startswith("$"):
                continue
            tokens = stripped.replace("'", "").replace('"', "").split()
            if not tokens:
                continue
            if tokens[0].upper() in ("RECT", "CURV"):
                gtype = tokens[0].upper()
                grid_line_idx = i
                break
        if grid_line_idx is None or gtype != "RECT":
            return None, None
        if grid_line_idx + 3 >= len(lines):
            return None, None
        values = lines[grid_line_idx + 1].split()
        Nx = int(float(values[0]))
        Ny = int(float(values[1]))
        values = lines[grid_line_idx + 2].split()
        dx = float(values[0]) / float(values[2])
        dy = float(values[1]) / float(values[2])
        values = lines[grid_line_idx + 3].split()
        lons = float(values[0]) / float(values[2])
        lats = float(values[1]) / float(values[2])
        lon1d = lons + np.arange(Nx) * dx
        lat1d = lats + np.arange(Ny) * dy
        lon, lat = np.meshgrid(lon1d, lat1d)
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


def _plot_pcolormesh_file(lon, lat, data, title, output_path, cmap="jet", shading="flat"):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=FIGSIZE_RECT)
    vmin = float(np.nanmin(data))
    vmax = float(np.nanmax(data))
    if vmin == vmax:
        vmax = vmin + 1.0
    if shading in ("interp", "gouraud"):
        im = ax.pcolormesh(lon, lat, data, cmap=cmap, vmin=vmin, vmax=vmax, shading="gouraud")
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
        im = ax.pcolormesh(lon_grid, lat_grid, data, cmap=cmap, vmin=vmin, vmax=vmax, shading="flat")
    ax.set_title(title, fontsize=14, fontweight="bold")
    ax.set_xlabel("Longitude", fontsize=12)
    ax.set_ylabel("Latitude", fontsize=12)
    ax.set_aspect("equal", adjustable="box")
    plt.colorbar(im, ax=ax).set_label(title, fontsize=10)
    plt.tight_layout()
    plt.savefig(output_path, dpi=OUTPUT_DPI, bbox_inches="tight")
    plt.close(fig)


def plot_structured_grid_structure(lon: np.ndarray, lat: np.ndarray, output_path: str) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    Ny, Nx = lon.shape
    fig, ax = plt.subplots(figsize=FIGSIZE_RECT)
    step = max(1, int(np.ceil(max(Nx, Ny) / STRUCTURED_MAX_LINES)))
    lw = max(0.15, 0.12 * (OUTPUT_DPI / 150.0))
    for j in range(0, Nx, step):
        ax.plot(lon[:, j], lat[:, j], "k-", linewidth=lw)
    for i in range(0, Ny, step):
        ax.plot(lon[i, :], lat[i, :], "k-", linewidth=lw)
    ax.set_title("Structured grid — layout", fontsize=14, fontweight="bold")
    ax.set_xlabel("Longitude", fontsize=12)
    ax.set_ylabel("Latitude", fontsize=12)
    ax.set_aspect("equal", adjustable="box")
    plt.tight_layout()
    plt.savefig(output_path, dpi=OUTPUT_DPI, bbox_inches="tight")
    plt.close(fig)


def run_unst(grid_dir: str) -> dict:
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
    emit_log(_viz_tr("step2_grid_viz_worker_read", "   正在读取网格数据…"))
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
    emit_log(_viz_tr("step2_grid_viz_worker_plot_bathy", "   正在绘制水深图…"))
    try:
        fig = plt.figure(figsize=fig_wh)
        ax = fig.add_subplot(1, 1, 1, projection=ccrs.PlateCarree())
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
        tpc = ax.tripcolor(
            triang,
            d,
            shading="gouraud",
            cmap="jet",
            vmin=vmin,
            vmax=vmax,
            transform=ccrs.PlateCarree(),
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
    emit_log(_viz_tr("step2_grid_viz_worker_plot_struct", "   正在绘制网格结构图…"))
    try:
        segs, _ = unst_wireframe_segments(xy, ect, tri_mask, STRUCTURE_MAX_EDGES)
        fig = plt.figure(figsize=fig_wh)
        ax = fig.add_subplot(1, 1, 1, projection=ccrs.PlateCarree())
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
    photo_dir = os.path.join(grid_dir, "photo", "grid")
    os.makedirs(photo_dir, exist_ok=True)
    fp_now = input_fingerprint(grid_dir, "structured")
    if fp_now and cache_is_current(grid_dir, "structured"):
        imgs = cached_image_paths(grid_dir, "structured")
        return {"ok": True, "skipped": True, "images": imgs, "photo_dir": photo_dir}
    emit_log(_viz_tr("step2_grid_viz_worker_read", "   正在读取网格数据…"))
    gf = {
        "meta": os.path.join(grid_dir, "grid.meta"),
        "bot": os.path.join(grid_dir, "grid.bot"),
        "mask": os.path.join(grid_dir, "grid.mask"),
        "obst": os.path.join(grid_dir, "grid.obst"),
    }
    for k, p in gf.items():
        if not os.path.isfile(p):
            return {"ok": False, "error": f"missing {k}", "images": [], "photo_dir": photo_dir}
    lon, lat = read_ww3meta(gf["meta"])
    if lon is None:
        return {"ok": False, "error": "grid.meta RECT read failed", "images": [], "photo_dir": photo_dir}
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
    emit_log(_viz_tr("step2_grid_viz_worker_plot_bathy", "   正在绘制水深图…"))
    try:
        p_bathy = os.path.join(photo_dir, "grid_bathymetry.png")
        _plot_pcolormesh_file(lon, lat, depth, "Bathymetry", p_bathy, shading="gouraud")
        written.append("grid_bathymetry.png")
    except Exception as e:
        return {"ok": False, "error": f"bathy: {e}", "images": [], "photo_dir": photo_dir}
    emit_log(_viz_tr("step2_grid_viz_worker_plot_struct", "   正在绘制网格结构图…"))
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
    _ensure_worker_language()
    p = argparse.ArgumentParser(description="WW3Tool grid visualization worker")
    p.add_argument("--mode", choices=("unst", "structured"), required=True)
    p.add_argument("--grid-dir", required=True)
    args = p.parse_args()
    grid_dir = os.path.abspath(os.path.normpath(args.grid_dir))
    if args.mode == "unst":
        res = run_unst(grid_dir)
    else:
        res = run_structured(grid_dir)
    if not res.get("ok"):
        emit_log(res.get("error", "failed"))
    emit_result(res)
    sys.exit(0 if res.get("ok") else 1)


if __name__ == "__main__":
    main()
