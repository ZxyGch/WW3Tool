"""二维谱站点地图对话框。

在 matplotlib/cartopy 地图上展示二维谱输出站点位置。

[EN] 2D spectrum station map dialog.

Displays 2D spectral output station locations on a matplotlib/cartopy map.
"""

from __future__ import annotations

import os
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from workflows.support.translations import tr


class SpectrumStationMapDialog(QDialog):
    """二维谱站点地图对话框。

    [EN] 2D spectrum station map dialog.
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        spec_file: str = "",
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("plotting_spectrum_map_title", "二维谱站点分布"))
        self.resize(900, 700)
        self._spec_file = spec_file
        self._build_ui()
        self._render_map()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        self._canvas_container = QWidget()
        self._canvas_layout = QHBoxLayout(self._canvas_container)
        self._canvas_layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._canvas_container, 1)

        btn_bar = QHBoxLayout()
        btn_bar.addStretch()
        close_btn = QPushButton(tr("close", "关闭"))
        close_btn.clicked.connect(self.close)
        btn_bar.addWidget(close_btn)
        layout.addLayout(btn_bar)

    def _render_map(self) -> None:
        """从谱文件读取站点并渲染地图。

        [EN] Read stations from the spectrum file and render the map.
        """
        try:
            import numpy as np
            import cartopy.crs as ccrs
            import cartopy.feature as cfeature
            from matplotlib.figure import Figure
            from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
            from netCDF4 import Dataset

            if not self._spec_file or not os.path.exists(self._spec_file):
                self._show_no_data_figure()
                return

            with Dataset(self._spec_file, "r") as ds:
                if "longitude" not in ds.variables or "latitude" not in ds.variables:
                    self._show_no_data_figure()
                    return

                lon = np.array(ds.variables["longitude"][:]).flatten()
                lat = np.array(ds.variables["latitude"][:]).flatten()

                station_names = []
                if "station_name" in ds.variables:
                    try:
                        raw_names = np.array(ds.variables["station_name"][:])
                        n_stations = len(lon)
                        for row in raw_names[:n_stations]:
                            name = b"".join(row.tolist()).decode("utf-8", "ignore").strip()
                            station_names.append(name.replace("\x00", "").strip())
                    except Exception:
                        pass

            if len(lon) == 0:
                self._show_no_data_figure()
                return

            # 确定地图范围
            # [EN] Determine map extent
            margin = max((float(lon.max()) - float(lon.min())) * 0.1, 2.0)
            lon_min = float(lon.min()) - margin
            lon_max = float(lon.max()) + margin
            lat_min = float(lat.min()) - margin
            lat_max = float(lat.max()) + margin

            # 投影方式
            # [EN] Projection method
            if lon_min < 0 or lon_max < 0:
                proj = ccrs.Mercator(central_longitude=180)
            else:
                proj = ccrs.Mercator(central_longitude=0)

            fig = Figure(figsize=(12, 10), dpi=100)
            ax = fig.add_subplot(1, 1, 1, projection=proj)
            ax.set_extent([lon_min, lon_max, lat_min, lat_max], crs=ccrs.PlateCarree())

            ax.add_feature(cfeature.OCEAN, facecolor="#a4d6ff")
            ax.add_feature(cfeature.LAND, facecolor="#f0f0f0")
            ax.coastlines(resolution="10m", linewidth=0.6)

            # 绘制站点
            # [EN] Plot stations
            for i, (s_lon, s_lat) in enumerate(zip(lon, lat)):
                ax.plot(float(s_lon), float(s_lat), "ro", markersize=10,
                        transform=ccrs.PlateCarree(),
                        label=tr("plotting_station_point", "站点") if i == 0 else "")
                name = station_names[i] if i < len(station_names) else str(i)
                ax.text(float(s_lon), float(s_lat), f"  {name}",
                        transform=ccrs.PlateCarree(), fontsize=9,
                        bbox=dict(boxstyle="round,pad=0.3", facecolor="yellow", alpha=0.7))

            if len(lon) > 0:
                ax.legend(loc="upper right")

            gl = ax.gridlines(crs=ccrs.PlateCarree(), draw_labels=True,
                              linewidth=0.5, color="gray", alpha=0.5, linestyle="--")
            gl.top_labels = False
            gl.right_labels = False

            title_base = tr("plotting_spectrum_stations_distribution", "二维谱站点分布")
            ax.set_title(f"{title_base}（{tr('plotting_total', '共')}{len(lon)}{tr('plotting_points_unit', '个点位')}）",
                         fontsize=14, fontweight="bold")
            fig.subplots_adjust(left=0.01, right=0.995, top=0.955, bottom=0.05)

            canvas = FigureCanvas(fig)
            canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            self._canvas_layout.addWidget(canvas)

        except ImportError:
            self._show_no_data_figure(tr("plotting_cartopy_required", "需要安装 cartopy 库才能显示站点地图"))

    def _show_no_data_figure(self, message: Optional[str] = None) -> None:
        """显示无数据提示。

        [EN] Display a no-data message.
        """
        try:
            from matplotlib.figure import Figure
            from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
            from PyQt6.QtWidgets import QSizePolicy

            fig = Figure(figsize=(10, 8), dpi=100)
            ax = fig.add_subplot(111)
            text = message or tr("plotting_no_spectrum_stations", "未找到有效的谱站点数据")
            ax.text(0.5, 0.5, text, ha="center", va="center", fontsize=14, transform=ax.transAxes)
            ax.set_axis_off()
            canvas = FigureCanvas(fig)
            canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            self._canvas_layout.addWidget(canvas)
        except ImportError:
            pass

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)
