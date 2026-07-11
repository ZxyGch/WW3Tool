"""第三步「在地图上选点」对话框。

进程内嵌入 cartopy + matplotlib 画布（与 src step3 一致），点击地图按经纬度选点，
支持多选、删除上一个点；确定后 ``result_points`` 为编辑后的完整点位列表。

为隔离全局状态，使用 ``Figure`` + ``FigureCanvasQTAgg`` 直接嵌入（不经 pyplot）。
matplotlib/cartopy 缺失时构造抛 ``ImportError``，由调用方降级提示。

[EN] Step 3 "Select Points on Map" dialog.
"""

from __future__ import annotations

import copy

import numpy as np
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
from workflows.domain.grid_bounds import (
    GLOBAL_LAT,
    GLOBAL_LON,
    lon_span_deg,
    normalize_longitude,
    point_in_lon_lat_bounds,
    regional_map_extent,
)
from workflows.support.translations import tr

_TITLE = "在地图上选点（点击地图选择点位，可多选）"


class MapPointPickerDialog(MessageBoxBase):
    """卡片式选点对话框：左侧地图画布，右侧确认/取消/删除上一个点。

    [EN] Card-style point-picker dialog: map canvas on the left, confirm / cancel /
    delete-last-point buttons on the right.
    """

    def __init__(
        self,
        parent=None,
        *,
        bounds: dict,
        existing_points: list[dict] | None = None,
        button_style: str = "",
    ) -> None:
        super().__init__(parent)
        from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
        from matplotlib.figure import Figure
        import cartopy.crs as ccrs
        import cartopy.feature as cfeature

        self._ccrs = ccrs
        self._cfeature = cfeature
        self._bounds = bounds
        self.result_points: list[dict] = []
        self._points: list[dict] = [copy.deepcopy(p) for p in (existing_points or [])]
        self._initial_count = len(self._points)

        self.setWindowTitle("")
        self.hideYesButton()
        self.hideCancelButton()
        self.buttonLayout.parent().setVisible(False)
        if hasattr(self, "setClosableOnMaskClicked"):
            self.setClosableOnMaskClicked(False)
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self).activated.connect(self._reject)

        map_meta = regional_map_extent(
            [bounds["lon_min"], bounds["lon_max"]],
            [bounds["lat_min"], bounds["lat_max"]],
            padding_frac=0.1,
            min_padding_deg=2.0,
        )
        self._ext = list(map_meta["extent"])  # type: ignore[arg-type]
        self._central_lon = float(map_meta["central_lon"])
        self._is_global_view = self._ext == [GLOBAL_LON[0], GLOBAL_LON[1], GLOBAL_LAT[0], GLOBAL_LAT[1]]

        _configure_cjk_fonts()
        self._fig = Figure(figsize=(10, 8), dpi=100)
        self._canvas = FigureCanvas(self._fig)
        self._canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        if self._is_global_view:
            projection = ccrs.PlateCarree()
        else:
            projection = ccrs.PlateCarree(central_longitude=self._central_lon)
        self._ax = self._fig.add_subplot(1, 1, 1, projection=projection)
        self._canvas.mpl_connect("button_press_event", self._on_click)

        content = QWidget()
        row = QHBoxLayout(content)
        row.setContentsMargins(2, 2, 2, 2)
        row.setSpacing(6)
        row.addWidget(self._canvas, 1)
        buttons = QVBoxLayout()
        buttons.setSpacing(8)
        buttons.addStretch(1)
        confirm = PrimaryPushButton(tr("step3_confirm_add_point", "确认并添加点位"))
        confirm.clicked.connect(self._accept)
        cancel = PrimaryPushButton(tr("cancel", "取消"))
        cancel.clicked.connect(self._reject)
        self._delete_last_btn = PrimaryPushButton(tr("step3_delete_last_point", "删除上一个点"))
        self._delete_last_btn.clicked.connect(self._delete_last)
        for btn in (confirm, cancel, self._delete_last_btn):
            btn.setAutoDefault(False)
            btn.setDefault(False)
            if button_style:
                btn.setStyleSheet(button_style)
            buttons.addWidget(btn)
        buttons.addStretch(1)
        holder = QWidget()
        holder.setLayout(buttons)
        width = max(160, confirm.sizeHint().width() + 24)
        holder.setFixedWidth(width)
        row.addWidget(holder, 0)

        self.viewLayout.setContentsMargins(8, 8, 8, 8)
        self.viewLayout.addWidget(content, 1)

        self._refresh_map()
        self._update_delete_button()

    # ── map drawing / interaction ──────────────────────────────────────────

    def _draw_base_map(self) -> None:
        ccrs = self._ccrs
        cfeature = self._cfeature
        self._ax.clear()
        self._ax.set_extent(self._ext, crs=ccrs.PlateCarree())
        try:
            self._ax.add_feature(cfeature.OCEAN, facecolor="#a4d6ff")
            self._ax.add_feature(cfeature.LAND, facecolor="#f0f0f0")
            self._ax.coastlines(resolution="50m", linewidth=0.6)
        except Exception:
            pass
        self._draw_grid_boxes()
        try:
            gl = self._ax.gridlines(draw_labels=True, linewidth=0.5, color="gray", alpha=0.5, linestyle="--")
            gl.top_labels = False
            gl.right_labels = False
        except Exception:
            pass
        self._ax.set_title(tr("step3_select_on_map_subtitle", _TITLE), fontsize=13, fontweight="bold")
        self._fig.subplots_adjust(left=0.04, right=0.99, top=0.94, bottom=0.05)

    def _draw_grid_boxes(self) -> None:
        from matplotlib import cm

        ccrs = self._ccrs
        levels = self._bounds.get("levels")
        if not levels:
            b = self._bounds
            levels = [
                {
                    "lon_min": b["lon_min"],
                    "lon_max": b["lon_max"],
                    "lat_min": b["lat_min"],
                    "lat_max": b["lat_max"],
                    "label": tr("step3_map_grid_range", "网格范围"),
                }
            ]
        n = len(levels)
        for i, lv in enumerate(levels):
            west = float(lv["lon_min"])
            east = float(lv["lon_max"])
            south = float(lv["lat_min"])
            north = float(lv["lat_max"])
            if lon_span_deg((west, east)) >= 359.0 and abs(north - south) >= 179.0:
                continue
            color = cm.rainbow(i / max(n - 1, 1))
            bx = [
                lv["lon_min"],
                lv["lon_max"],
                lv["lon_max"],
                lv["lon_min"],
                lv["lon_min"],
            ]
            by = [
                lv["lat_min"],
                lv["lat_min"],
                lv["lat_max"],
                lv["lat_max"],
                lv["lat_min"],
            ]
            self._ax.plot(
                bx,
                by,
                transform=ccrs.PlateCarree(),
                color=color,
                linewidth=2,
                linestyle="--",
                label=str(lv.get("label", f"level{i}")),
            )
        if n > 1:
            self._ax.legend(loc="upper right", fontsize=8)

    def _draw_points(self) -> None:
        ccrs = self._ccrs
        for i, p in enumerate(self._points):
            is_new = i >= self._initial_count
            color = "red" if is_new else "green"
            face = "yellow" if is_new else "lightgreen"
            self._ax.plot(
                p["lon"],
                p["lat"],
                marker="o",
                color=color,
                linestyle="None",
                markersize=8 if is_new else 6,
                transform=ccrs.PlateCarree(),
            )
            self._ax.text(
                p["lon"] + 0.3,
                p["lat"] + 0.3,
                str(p.get("name", "")),
                transform=ccrs.PlateCarree(),
                fontsize=9 if is_new else 8,
                bbox=dict(boxstyle="round,pad=0.3", facecolor=face, alpha=0.7),
            )

    def _refresh_map(self) -> None:
        self._draw_base_map()
        self._draw_points()
        self._canvas.draw()

    def _update_delete_button(self) -> None:
        self._delete_last_btn.setEnabled(bool(self._points))

    def _click_lon_lat(self, event) -> tuple[float, float] | None:
        """Map canvas click to geographic lon/lat (PlateCarree)."""
        if event.inaxes != self._ax or event.xdata is None or event.ydata is None:
            return None
        lon, lat = self._ccrs.Geodetic().transform_point(
            event.xdata,
            event.ydata,
            self._ax.projection,
        )
        lon = float(lon)
        lat = float(lat)
        if np.isnan(lon) or np.isnan(lat):
            return None
        return lon, lat

    def _on_click(self, event) -> None:
        clicked = self._click_lon_lat(event)
        if clicked is None:
            return
        lon, lat = clicked
        lon = normalize_longitude(lon)
        b = self._bounds
        if not point_in_lon_lat_bounds(
            lon,
            lat,
            lon_min=b["lon_min"],
            lon_max=b["lon_max"],
            lat_min=b["lat_min"],
            lat_max=b["lat_max"],
        ):
            return
        for p in self._points:
            if abs(p["lon"] - lon) < 1e-3 and abs(p["lat"] - lat) < 1e-3:
                return
        name = str(len(self._points))
        self._points.append({"lon": float(lon), "lat": float(lat), "name": name})
        self._refresh_map()
        self._update_delete_button()

    def _delete_last(self) -> None:
        if not self._points:
            return
        self._points.pop()
        self._refresh_map()
        self._update_delete_button()

    # ── result / close ──────────────────────────────────────────────────────

    def _accept(self) -> None:
        self.result_points = [copy.deepcopy(p) for p in self._points]
        QDialog.done(self, int(QDialog.DialogCode.Accepted))

    def _reject(self) -> None:
        QDialog.done(self, int(QDialog.DialogCode.Rejected))

    # ── card sizing (mirror Step 2 map view) ─────────────────────────────────

    def showEvent(self, event):
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
    try:
        from workflows.infrastructure.grid_visualization.worker import _configure_matplotlib_cjk_fonts

        _configure_matplotlib_cjk_fonts()
    except Exception:
        pass
