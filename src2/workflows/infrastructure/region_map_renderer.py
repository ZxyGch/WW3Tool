"""将配置的网格区域渲染为地理 PNG 预览图。

在 Step 2 网格设置阶段，根据 ``GridConfig`` 中外/内（嵌套）矩形范围，
用 cartopy 绘制 Mercator 底图与范围框，供用户确认模拟域位置。
"""

from __future__ import annotations

import platform
from pathlib import Path

from ..domain.config_models import GridConfig


def render_region_map_png(grid: GridConfig, output_path: Path) -> None:
    """渲染外网格（及嵌套时的内网格）范围预览 PNG。

    figsize 根据地图内容实际宽高比动态计算，使 PNG 与内容比例一致，
    避免在对话框中出现大量空白边距。

    参数:
        grid: 含 outer/inner 经纬度范围的网格配置
        output_path: 输出 PNG 路径（父目录需已存在或由调用方创建）
    """
    import math

    import matplotlib

    matplotlib.use("Agg")
    import cartopy.crs as ccrs
    import cartopy.feature as cfeature
    import matplotlib.pyplot as plt

    _configure_chinese_font(matplotlib)
    outer = grid.outer
    inner = grid.inner if grid.grid_type == "nested" else None
    all_lon = list(outer.lon) + (list(inner.lon) if inner else [])
    all_lat = list(outer.lat) + (list(inner.lat) if inner else [])
    extent = [min(all_lon) - 2, max(all_lon) + 2, min(all_lat) - 2, max(all_lat) + 2]

    # Calculate figure size to match the map's geographic aspect ratio so the
    # rendered PNG fills the dialog without extra white margins.
    lat_center = (extent[2] + extent[3]) / 2.0
    lon_span = max(extent[1] - extent[0], 1e-6)
    lat_span = max(extent[3] - extent[2], 1e-6)
    cos_ref = max(abs(math.cos(math.radians(lat_center))), 0.08)
    aspect_wh = max(0.2, min((lon_span * cos_ref) / lat_span, 14.0))
    fig_base = 8.0
    fig_min = 3.5
    if aspect_wh >= 1.0:
        fig_w = max(fig_base, fig_min * aspect_wh)
        fig_h = fig_w / aspect_wh
    else:
        fig_h = max(fig_base, fig_min / aspect_wh)
        fig_w = fig_h * aspect_wh

    # 240 DPI covers Retina / HiDPI displays (2× logical-to-physical ratio)
    render_dpi = 240
    figure = plt.figure(figsize=(fig_w, fig_h), dpi=render_dpi)
    axis = figure.add_subplot(1, 1, 1, projection=ccrs.Mercator())
    axis.set_extent(extent, crs=ccrs.PlateCarree())
    axis.add_feature(cfeature.OCEAN, facecolor="#a4d6ff")
    axis.add_feature(cfeature.LAND, facecolor="#e6e6e6")
    axis.coastlines(resolution="10m", linewidth=0.5)

    transform = ccrs.PlateCarree()
    _draw_rectangle(axis, outer.lon, outer.lat, "red", "外网格" if inner else "网格范围", transform)
    if inner is not None:
        _draw_rectangle(axis, inner.lon, inner.lat, "blue", "内网格", transform)
    axis.legend(loc="upper right", fontsize=10)

    lines = axis.gridlines(draw_labels=True, linewidth=0.8, color="gray", alpha=0.7, linestyle="--")
    lines.right_labels = False
    lines.top_labels = False
    figure.subplots_adjust(left=0.11, right=0.98, bottom=0.10, top=0.96)
    figure.savefig(str(output_path), dpi=render_dpi)
    plt.close(figure)


def _configure_chinese_font(matplotlib) -> None:
    """按操作系统选择可用 CJK 字体，避免图例/标题缺字。"""
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


def _draw_rectangle(axis, lon: list[float], lat: list[float], color: str, label: str, transform) -> None:
    """在地图上绘制经纬度矩形框并加入图例。"""
    import matplotlib.pyplot as plt

    rectangle = plt.Rectangle(
        (lon[0], lat[0]),
        lon[1] - lon[0],
        lat[1] - lat[0],
        linewidth=1.0,
        edgecolor=color,
        facecolor="none",
        linestyle="--",
        transform=transform,
        label=label,
    )
    axis.add_patch(rectangle)
