#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
第二步「查看区域地图」子进程：使用 Agg 渲染 PNG，避免阻塞主界面。
用法: python region_map_worker.py <config.json> <output.png>
"""
from __future__ import annotations

import json
import sys
import warnings

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import cartopy.crs as ccrs
import cartopy.feature as cfeature

# 默认 10m 岸线；若嫌慢可在 cfg 中设 coastline_resolution 为 "50m" 或 "110m"
_DEFAULT_COAST_RES = "10m"


def render_region_map_png(cfg: dict, out_png: str) -> None:
    display = cfg["display_extent"]
    dlon_min, dlon_max, dlat_min, dlat_max = display
    central_lon = int(cfg.get("central_longitude", 0))
    if central_lon not in (0, 180):
        central_lon = 0

    fig_w = float(cfg.get("fig_width_in", 9.0))
    fig_h = float(cfg.get("fig_height_in", 6.0))
    dpi = int(cfg.get("dpi", 100))

    chinese_font = cfg.get("chinese_font")

    if chinese_font:
        plt.rcParams["font.sans-serif"] = [chinese_font]
        plt.rcParams["axes.unicode_minus"] = False
    else:
        warnings.filterwarnings("ignore", category=UserWarning, module="cartopy")

    proj = ccrs.Mercator(central_longitude=central_lon)
    fig = plt.figure(figsize=(fig_w, fig_h), dpi=dpi)
    ax = fig.add_subplot(1, 1, 1, projection=proj)
    ax.set_extent([dlon_min, dlon_max, dlat_min, dlat_max], crs=ccrs.PlateCarree())

    # Cartopy 默认 LAND/OCEAN 为 50m 填充，与 10m 岸线搭配观感一致
    ax.add_feature(cfeature.OCEAN, facecolor="#a4d6ff")
    ax.add_feature(cfeature.LAND, facecolor="#e6e6e6")
    coast_res = str(cfg.get("coastline_resolution", _DEFAULT_COAST_RES))
    if coast_res not in ("10m", "50m", "110m"):
        coast_res = _DEFAULT_COAST_RES
    ax.coastlines(resolution=coast_res, linewidth=0.5)

    plate_carree = ccrs.PlateCarree()
    is_nested = bool(cfg.get("is_nested"))
    outer = cfg["outer_rect"]
    ox0, ox1, oy0, oy1 = outer

    if is_nested:
        inner = cfg["inner_rect"]
        ix0, ix1, iy0, iy1 = inner
        outer_rect = plt.Rectangle(
            (ox0, oy0),
            ox1 - ox0,
            oy1 - oy0,
            linewidth=1.0,
            edgecolor="red",
            facecolor="none",
            linestyle="--",
            transform=plate_carree,
            label=str(cfg.get("label_outer", "outer")),
        )
        ax.add_patch(outer_rect)
        inner_rect = plt.Rectangle(
            (ix0, iy0),
            ix1 - ix0,
            iy1 - iy0,
            linewidth=1.0,
            edgecolor="blue",
            facecolor="none",
            linestyle="--",
            transform=plate_carree,
            label=str(cfg.get("label_inner", "inner")),
        )
        ax.add_patch(inner_rect)
        ax.legend(loc="upper right", fontsize=10)
    else:
        outer_rect = plt.Rectangle(
            (ox0, oy0),
            ox1 - ox0,
            oy1 - oy0,
            linewidth=1.0,
            edgecolor="red",
            facecolor="none",
            linestyle="--",
            transform=plate_carree,
            label=str(cfg.get("label_single", "range")),
        )
        ax.add_patch(outer_rect)
        ax.legend(loc="upper right", fontsize=10)

    gl = ax.gridlines(
        draw_labels=True,
        linewidth=0.8,
        color="gray",
        alpha=0.7,
        linestyle="--",
    )
    gl.left_labels = True
    gl.bottom_labels = True
    gl.right_labels = False
    gl.top_labels = False

    if chinese_font:
        try:
            gl.xlabel_style = {"fontname": chinese_font}
            gl.ylabel_style = {"fontname": chinese_font}
        except Exception:
            pass

    fig.subplots_adjust(left=0.11, right=0.98, bottom=0.10, top=0.96)
    fig.savefig(out_png, dpi=dpi)
    plt.close(fig)


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: region_map_worker.py <config.json> <output.png>", file=sys.stderr)
        return 2
    cfg_path, out_png = sys.argv[1], sys.argv[2]
    try:
        with open(cfg_path, encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception as e:
        print(f"config: {e}", file=sys.stderr)
        return 1
    try:
        render_region_map_png(cfg, out_png)
    except Exception as e:
        print(str(e), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
