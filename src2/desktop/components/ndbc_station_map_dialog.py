"""NDBC 浮标站点地图对话框（对齐 src ``plot_ndbc._show_ndbc_station_map``）。"""

from __future__ import annotations

import platform
from typing import List

import numpy as np
from PyQt6 import QtCore, QtWidgets
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from qfluentwidgets import MessageBoxBase, PrimaryPushButton

from workflows.support.translations import tr


class NDBCStationMapDialog(MessageBoxBase):
    """在地图上展示 NDBC 浮标站点，支持切换站点名称标签。"""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        stations: List[dict],
        lon_lat: List[float],
        content_aspect_wh: float = 1.25,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("")
        self._content_aspect_wh = float(content_aspect_wh) if content_aspect_wh > 0 else 1.25
        if platform.system() == "Darwin":
            self.setStyleSheet("font-family: 'PingFang SC';")

        self.hideYesButton()
        self.hideCancelButton()
        self.buttonLayout.parent().setVisible(False)

        self._content_host = QWidget()
        self._content_host.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._content_layout = QVBoxLayout(self._content_host)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(0)
        self.viewLayout.addWidget(self._content_host, 1)

        esc = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        esc.activated.connect(self._close_dialog)

        if hasattr(self, "setClosableOnMaskClicked"):
            self.setClosableOnMaskClicked(True)

        self._build_map(stations, lon_lat)

    def _close_dialog(self) -> None:
        QtWidgets.QDialog.done(self, int(QtWidgets.QDialog.DialogCode.Rejected))

    def _avail_rect(self) -> tuple[int, int]:
        parent = self.parentWidget()
        ratio_w, ratio_h = 0.88, 0.88
        if parent is not None and parent.isVisible():
            pr = parent.frameGeometry()
            return int(pr.width() * ratio_w), int(pr.height() * ratio_h)
        screen = QtWidgets.QApplication.primaryScreen()
        ag = screen.availableGeometry() if screen is not None else None
        if ag is not None:
            return int(ag.width() * 0.86), int(ag.height() * 0.88)
        return 1240, 920

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        QtCore.QTimer.singleShot(0, self._fit_to_parent_window)

    def _fit_to_parent_window(self) -> None:
        avail_w, avail_h = self._avail_rect()
        min_w, min_h = 960, 640
        max_w, max_h = 1920, 1080
        aspect = float(np.clip(self._content_aspect_wh, 0.3, 14.0))
        if avail_w / max(avail_h, 1) > aspect:
            dialog_h = avail_h
            dialog_w = int(round(dialog_h * aspect))
        else:
            dialog_w = avail_w
            dialog_h = int(round(dialog_w / aspect))
        dialog_w = max(min_w, min(dialog_w, max_w))
        dialog_h = max(min_h, min(dialog_h, max_h))
        card = getattr(self, "widget", None)
        if card is not None:
            card.setFixedSize(dialog_w, dialog_h)
            card.updateGeometry()
        else:
            self.resize(dialog_w, dialog_h)

    def _build_map(self, stations: List[dict], lon_lat: List[float]) -> None:
        import cartopy.crs as ccrs
        import cartopy.feature as cfeature
        import matplotlib.pyplot as plt

        from workflows.infrastructure.plot.ndbc_worker import _configure_ndbc_map_fonts

        _configure_ndbc_map_fonts()

        lon_min, lon_max, lat_min, lat_max = lon_lat
        lon_pad = max(1.0, abs(lon_max - lon_min) * 0.1)
        lat_pad = max(1.0, abs(lat_max - lat_min) * 0.1)

        fig = plt.figure(figsize=(10, 6))
        ax = plt.axes(projection=ccrs.PlateCarree())
        ax.set_extent(
            [
                min(lon_min, lon_max) - lon_pad,
                max(lon_min, lon_max) + lon_pad,
                min(lat_min, lat_max) - lat_pad,
                max(lat_min, lat_max) + lat_pad,
            ],
            crs=ccrs.PlateCarree(),
        )
        ax.add_feature(cfeature.LAND, facecolor="lightgray")
        ax.add_feature(cfeature.COASTLINE)
        ax.add_feature(cfeature.BORDERS, linestyle=":")
        gl = ax.gridlines(draw_labels=True, linestyle="--", alpha=0.5)
        gl.top_labels = False
        gl.right_labels = False

        lons = [station["lon"] for station in stations]
        lats = [station["lat"] for station in stations]
        ax.scatter(lons, lats, color="green", s=10, transform=ccrs.PlateCarree(), zorder=3)

        text_labels = []
        for station in stations:
            label = station.get("id") or station.get("name") or "-"
            txt = ax.text(
                station["lon"],
                station["lat"],
                label,
                transform=ccrs.PlateCarree(),
                fontsize=8,
                color="black",
                zorder=4,
                ha="left",
                va="bottom",
            )
            text_labels.append(txt)

        ax.set_title(
            tr("plotting_ndbc_station_distribution", "NDBC 浮标点位分布"),
            fontsize=14,
            fontweight="bold",
        )
        fig.subplots_adjust(left=0.02, right=0.98, top=0.93, bottom=0.06)

        content_widget = QWidget()
        layout = QHBoxLayout(content_widget)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(6)

        canvas = FigureCanvas(fig)
        canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(canvas, 1)

        button_layout = QVBoxLayout()
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(6)
        button_layout.addStretch()

        toggle_labels_btn = PrimaryPushButton(tr("plotting_hide_station_labels", "隐藏站点名称"))
        labels_visible = True

        def toggle_station_labels() -> None:
            nonlocal labels_visible
            labels_visible = not labels_visible
            for text in text_labels:
                text.set_visible(labels_visible)
            toggle_labels_btn.setText(
                tr("plotting_hide_station_labels", "隐藏站点名称")
                if labels_visible
                else tr("plotting_show_station_labels", "显示站点名称")
            )
            canvas.draw_idle()

        toggle_labels_btn.clicked.connect(toggle_station_labels)
        button_layout.addWidget(toggle_labels_btn)
        button_layout.addStretch()
        layout.addLayout(button_layout)

        canvas.draw()
        content_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._content_layout.addWidget(content_widget, 1)
        self._fig = fig

    def closeEvent(self, event) -> None:  # noqa: N802
        if hasattr(self, "_fig"):
            import matplotlib.pyplot as plt

            plt.close(self._fig)
        super().closeEvent(event)
