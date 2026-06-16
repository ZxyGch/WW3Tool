"""二维谱站点地图对话框。

在 matplotlib/cartopy 地图上展示二维谱输出站点位置。采用与第三步「在地图上选点」
（:class:`MapPointPickerDialog`）一致的卡片式弹窗样式（``MessageBoxBase`` 遮罩卡片），
站点以绿色圆点标注。仅展示，不可交互选点。

matplotlib/cartopy 缺失时构造抛 ``ImportError``，由调用方降级提示。

[EN] 2D spectrum station map dialog.

Displays 2D spectral output station locations on a matplotlib/cartopy map, using the
same card-style popup (``MessageBoxBase`` masked card) as the Step-3 "Select Points on
Map" dialog (:class:`MapPointPickerDialog`). Stations are marked with green dots.
Display-only (no interactive picking). If matplotlib/cartopy is missing, construction
raises ``ImportError`` for the caller to handle.
"""

from __future__ import annotations

import os

from PyQt6 import QtCore
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import MessageBoxBase, PrimaryPushButton

from workflows.support.translations import tr


class SpectrumStationMapDialog(MessageBoxBase):
    """卡片式二维谱站点地图对话框（绿色站点），样式与第三步地图选点一致。

    [EN] Card-style 2D spectrum station map dialog (green stations), matching the
    Step-3 map point picker style.
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        spec_file: str = "",
        button_style: str = "",
    ) -> None:
        super().__init__(parent)
        # 延迟导入：缺依赖时由调用方捕获 ImportError 降级。
        # [EN] Lazy import; caller catches ImportError for graceful degradation.
        from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
        from matplotlib.figure import Figure
        import cartopy.crs as ccrs

        self._ccrs = ccrs
        self._spec_file = spec_file

        self.setWindowTitle("")
        self.hideYesButton()
        self.hideCancelButton()
        self.buttonLayout.parent().setVisible(False)
        if hasattr(self, "setClosableOnMaskClicked"):
            self.setClosableOnMaskClicked(True)
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self).activated.connect(self._close)

        _configure_cjk_fonts()
        self._fig = Figure(figsize=(10, 8), dpi=100)
        self._canvas = FigureCanvas(self._fig)
        self._canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self._render_map()

        # ── 布局：左画布 + 右关闭按钮（与选点对话框一致）──
        # [EN] Layout: left canvas + right close button (mirrors the picker)
        content = QWidget()
        row = QHBoxLayout(content)
        row.setContentsMargins(2, 2, 2, 2)
        row.setSpacing(6)
        row.addWidget(self._canvas, 1)
        buttons = QVBoxLayout()
        buttons.setSpacing(8)
        buttons.addStretch(1)
        close_btn = PrimaryPushButton(tr("close", "关闭"))
        close_btn.clicked.connect(self._close)
        if button_style:
            close_btn.setStyleSheet(button_style)
        buttons.addWidget(close_btn)
        buttons.addStretch(1)
        holder = QWidget()
        holder.setLayout(buttons)
        holder.setFixedWidth(max(160, close_btn.sizeHint().width() + 24))
        row.addWidget(holder, 0)

        self.viewLayout.setContentsMargins(8, 8, 8, 8)
        self.viewLayout.addWidget(content, 1)

    # ── map drawing ─────────────────────────────────────────────────────────

    def _render_map(self) -> None:
        """从谱文件读取站点并渲染地图（绿色站点）。

        [EN] Read stations from the spectrum file and render them as green dots.
        """
        import numpy as np
        import cartopy.crs as ccrs
        import cartopy.feature as cfeature
        from netCDF4 import Dataset
        from workflows.infrastructure.plot.workers_utils import (
            _collect_station_lon_lat,
            _decode_station_names,
        )

        if not self._spec_file or not os.path.exists(self._spec_file):
            self._show_no_data(tr("plotting_no_spectrum_stations", "未找到有效的谱站点数据"))
            return

        with Dataset(self._spec_file, "r") as ds:
            if "longitude" not in ds.variables or "latitude" not in ds.variables:
                self._show_no_data(tr("plotting_no_spectrum_stations", "未找到有效的谱站点数据"))
                return
            if "station" in ds.dimensions:
                n_stations = len(ds.dimensions["station"])
            else:
                n_stations = len(ds.variables["longitude"]) if hasattr(ds.variables["longitude"], "__len__") else 1
            lon_data = np.array(ds.variables["longitude"][:])
            lat_data = np.array(ds.variables["latitude"][:])
            points = _collect_station_lon_lat(lon_data, lat_data, n_stations)
            station_names = []
            if "station_name" in ds.variables:
                station_names = _decode_station_names(ds.variables["station_name"][:], n_stations) or []

        if not points:
            self._show_no_data(tr("plotting_no_spectrum_stations", "未找到有效的谱站点数据"))
            return

        lon = np.array([point[0] for point in points], dtype=float)
        lat = np.array([point[1] for point in points], dtype=float)

        margin = max(
            (float(lon.max()) - float(lon.min())) * 0.1,
            (float(lat.max()) - float(lat.min())) * 0.1,
            2.0,
        )
        ext = [
            float(lon.min()) - margin,
            float(lon.max()) + margin,
            float(lat.min()) - margin,
            float(lat.max()) + margin,
        ]

        ax = self._fig.add_subplot(1, 1, 1, projection=ccrs.PlateCarree(central_longitude=0.5 * (ext[0] + ext[1])))
        ax.set_extent(ext, crs=ccrs.PlateCarree())
        try:
            ax.add_feature(cfeature.OCEAN, facecolor="#a4d6ff")
            ax.add_feature(cfeature.LAND, facecolor="#f0f0f0")
            ax.coastlines(resolution="50m", linewidth=0.6)
        except Exception:
            pass

        # 绿色站点 [EN] green station dots
        for i, (s_lon, s_lat) in enumerate(points):
            ax.plot(
                float(s_lon), float(s_lat), "go", markersize=8,
                transform=ccrs.PlateCarree(),
                label=tr("plotting_station_point", "站点") if i == 0 else "",
            )
            name = station_names[i] if i < len(station_names) else str(i)
            ax.text(
                float(s_lon) + 0.3, float(s_lat) + 0.3, str(name),
                transform=ccrs.PlateCarree(), fontsize=8,
                bbox=dict(boxstyle="round,pad=0.3", facecolor="lightgreen", alpha=0.7),
            )

        ax.legend(loc="upper right")
        try:
            gl = ax.gridlines(crs=ccrs.PlateCarree(), draw_labels=True,
                              linewidth=0.5, color="gray", alpha=0.5, linestyle="--")
            gl.top_labels = False
            gl.right_labels = False
        except Exception:
            pass

        title_base = tr("plotting_spectrum_stations_distribution", "二维谱站点分布")
        ax.set_title(
            f"{title_base}（{tr('plotting_total', '共')}{len(points)}{tr('plotting_points_unit', '个点位')}）",
            fontsize=13, fontweight="bold",
        )
        self._fig.subplots_adjust(left=0.04, right=0.99, top=0.94, bottom=0.05)

    def _show_no_data(self, message: str) -> None:
        """在画布上显示无数据提示。[EN] Show a no-data message on the canvas."""
        self._fig.clf()
        ax = self._fig.add_subplot(111)
        ax.text(0.5, 0.5, message, ha="center", va="center", fontsize=14, transform=ax.transAxes)
        ax.set_axis_off()

    # ── close / sizing (mirror MapPointPickerDialog) ─────────────────────────

    def _close(self) -> None:
        QDialog.done(self, int(QDialog.DialogCode.Accepted))

    def showEvent(self, event):  # noqa: N802
        super().showEvent(event)
        QtCore.QTimer.singleShot(0, self._fit)

    def _fit(self) -> None:
        parent = self.parentWidget()
        if parent is not None and parent.isVisible():
            pr = parent.frameGeometry()
            avail_w, avail_h = int(pr.width() * 0.88), int(pr.height() * 0.88)
        else:
            screen = QApplication.primaryScreen()
            ag = screen.availableGeometry() if screen is not None else None
            avail_w, avail_h = (int(ag.width() * 0.86), int(ag.height() * 0.88)) if ag else (1240, 920)
        aspect = 1.25
        if avail_w / max(avail_h, 1) > aspect:
            dh = avail_h
            dw = int(round(dh * aspect))
        else:
            dw = avail_w
            dh = int(round(dw / aspect))
        dw = max(960, min(dw, 1920))
        dh = max(640, min(dh, 1080))
        card = getattr(self, "widget", None)
        if card is not None:
            card.setFixedSize(dw, dh)


def _configure_cjk_fonts() -> None:
    """复用网格可视化 worker 的 CJK 字体配置，避免标题缺字。

    [EN] Reuse the CJK font config from the grid visualization worker so the
    dialog title renders Chinese characters correctly.
    """
    try:
        from workflows.infrastructure.grid_visualization.worker import _configure_matplotlib_cjk_fonts

        _configure_matplotlib_cjk_fonts()
    except Exception:
        pass
