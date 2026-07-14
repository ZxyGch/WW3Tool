"""将配置的网格区域渲染为地理 PNG 预览图。

在 Step 1 网格设置阶段，根据 ``GridConfig`` 中外/内（嵌套）矩形范围，
用 cartopy 绘制底图与范围框，供用户确认模拟域位置。
近全球范围使用 PlateCarree，避免 Mercator 在极高纬度产生 NaN/Inf。

[EN] Render the configured grid region as a geographic PNG preview map.

During the Step 1 grid-setup stage, draw the basemap and domain bounding boxes from the outer/inner (nested) rectangles in ``GridConfig`` for the user to confirm the simulation domain location.
Near-global ranges use PlateCarree to avoid NaN/Inf from Mercator at very high latitudes.
"""

from __future__ import annotations

import platform
from pathlib import Path
from collections.abc import Sequence

from ..domain.config_models import GridConfig
from ..domain.grid_bounds import lon_span_deg, regional_map_extent


def render_region_map_png(grid: GridConfig, output_path: Path, *, labels: Sequence[str] | None = None) -> None:
    """渲染外网格（及嵌套时的内网格）范围预览 PNG。

    figsize 根据地图内容实际宽高比动态计算，使 PNG 与内容比例一致，
    避免在对话框中出现大量空白边距。

    参数:
        grid: 含 outer/inner 经纬度范围的网格配置
        output_path: 输出 PNG 路径（父目录需已存在或由调用方创建）
    
    [EN] Render a PNG preview of the outer grid (and inner grid when nested) extent.

    figsize is dynamically computed from the actual aspect ratio of the map content so that the PNG matches the content proportion and avoids large blank margins in dialogs.

    Parameters:
        grid: grid configuration containing outer/inner longitude/latitude ranges
        output_path: output PNG path (parent directory must exist or be created by caller)
    """
    import matplotlib

    matplotlib.use("Agg")
    import cartopy.crs as ccrs
    import cartopy.feature as cfeature
    import matplotlib.pyplot as plt

    _configure_chinese_font(matplotlib)
    levels = grid.nested_levels or [grid.outer]
    all_lon = [v for lv in levels for v in lv.lon]
    all_lat = [v for lv in levels for v in lv.lat]
    map_meta = regional_map_extent(
        [min(all_lon), max(all_lon)],
        [min(all_lat), max(all_lat)],
    )
    extent = list(map_meta["extent"])  # type: ignore[arg-type]
    central_lon = float(map_meta["central_lon"])
    projection = str(map_meta["projection"])
    aspect_wh = float(map_meta["aspect_wh"])

    fig_base = 8.0
    fig_min = 3.5
    if aspect_wh >= 1.0:
        fig_w = max(fig_base, fig_min * aspect_wh)
        fig_h = fig_w / aspect_wh
    else:
        fig_h = max(fig_base, fig_min / aspect_wh)
        fig_w = fig_h * aspect_wh

    render_dpi = 240
    figure = plt.figure(figsize=(fig_w, fig_h), dpi=render_dpi)
    if projection == "mercator":
        axis = figure.add_subplot(1, 1, 1, projection=ccrs.Mercator(central_longitude=central_lon))
    else:
        axis = figure.add_subplot(
            1, 1, 1, projection=ccrs.PlateCarree(central_longitude=central_lon)
        )
    axis.set_extent(extent, crs=ccrs.PlateCarree())
    axis.add_feature(cfeature.OCEAN, facecolor="#a4d6ff")
    axis.add_feature(cfeature.LAND, facecolor="#e6e6e6")
    axis.coastlines(resolution="10m", linewidth=0.5)

    transform = ccrs.PlateCarree()
    from matplotlib import cm

    n_levels = len(levels)
    for i, lv in enumerate(levels):
        color = cm.rainbow(i / max(n_levels - 1, 1))
        label = str(labels[i]) if labels and i < len(labels) else ("网格范围" if n_levels == 1 else f"level{i}")
        _draw_lon_lat_box(axis, lv.lon, lv.lat, color, label, transform)
    axis.legend(loc="upper right", fontsize=10)

    lines = axis.gridlines(draw_labels=True, linewidth=0.8, color="gray", alpha=0.7, linestyle="--")
    lines.right_labels = False
    lines.top_labels = False
    figure.subplots_adjust(left=0.11, right=0.98, bottom=0.10, top=0.96)
    figure.savefig(str(output_path), dpi=render_dpi)
    plt.close(figure)


def _configure_chinese_font(matplotlib) -> None:
    """按操作系统选择可用 CJK 字体，避免图例/标题缺字。

    [EN] Select an available CJK font according to the operating system to avoid missing glyphs in legends/titles.
    """
    from matplotlib import font_manager

    candidates = {
        "Darwin": ["PingFang SC", "Hiragino Sans GB", "Heiti SC", "Songti SC", "Arial Unicode MS"],
        "Windows": ["Microsoft YaHei", "Microsoft JhengHei", "SimHei", "SimSun"],
    }.get(
        platform.system(),
        ["Noto Sans CJK SC", "WenQuanYi Micro Hei", "Source Han Sans SC"],
    )
    available = {font.name for font in font_manager.fontManager.ttflist}
    selected = next((font for font in candidates if font in available), None)
    if selected:
        matplotlib.rcParams["font.sans-serif"] = [selected, "DejaVu Sans"]
        matplotlib.rcParams["axes.unicode_minus"] = False


def _draw_lon_lat_box(axis, lon: list[float], lat: list[float], color, label: str, transform) -> None:
    
    # Draw a longitude/latitude rectangle on the map and add it to the legend.
    """在地图上绘制经纬度矩形框并加入图例。"""
    import matplotlib.pyplot as plt

    west, east = float(lon[0]), float(lon[1])
    south, north = float(lat[0]), float(lat[1])
    if lon_span_deg((west, east)) >= 359.0 or abs(north - south) >= 179.0:
        xs = [west, east, east, west, west]
        ys = [south, south, north, north, south]
        axis.plot(xs, ys, color=color, linestyle="--", linewidth=1.0, transform=transform, label=label)
        return

    rectangle = plt.Rectangle(
        (west, south),
        east - west,
        north - south,
        linewidth=1.0,
        edgecolor=color,
        facecolor="none",
        linestyle="--",
        transform=transform,
        label=label,
    )
    axis.add_patch(rectangle)
