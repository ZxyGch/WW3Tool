"""第三步「在地图上选点」对话框。

进程内嵌入 cartopy + matplotlib 画布（与 src step3 一致），点击地图按经纬度选点，
支持多选、删除上一个点；确定后 ``selected_points`` 为新增点位列表
``[{"lon","lat","name"}, ...]``。点击落点按网格包围盒校验，越界忽略。

为隔离全局状态，使用 ``Figure`` + ``FigureCanvasQTAgg`` 直接嵌入（不经 pyplot）。
matplotlib/cartopy 缺失时构造抛 ``ImportError``，由调用方降级提示。

[EN] Step 3 "Select Points on Map" dialog.

Embeds a cartopy + matplotlib canvas in-process (consistent with src step3). Clicking
on the map selects points by lon/lat. Supports multi-select and deleting the last point.
On confirm, ``selected_points`` is a list of new points
``[{"lon","lat","name"}, ...]``. Clicks are validated against the grid bounding box;
out-of-bounds clicks are ignored.

To isolate global state, uses ``Figure`` + ``FigureCanvasQTAgg`` directly embedded
(not via pyplot). If matplotlib/cartopy is missing, construction raises ``ImportError``,
and the caller should handle graceful degradation.
"""

from __future__ import annotations

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
from workflows.support.translations import tr

_TITLE = "在地图上选点（点击地图选择点位，可多选）"


class MapPointPickerDialog(MessageBoxBase):
    """卡片式选点对话框：左侧地图画布，右侧确认/取消/删除上一个点。

    [EN] Card-style point selection dialog: map canvas on the left,
    confirm/cancel/delete-last-point buttons on the right.
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
        # 延迟导入：缺依赖时由调用方捕获 ImportError 降级。
        # [EN] Lazy import: when dependencies are missing, the caller catches
        # ImportError for graceful degradation.
        from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
        from matplotlib.figure import Figure
        import cartopy.crs as ccrs
        import cartopy.feature as cfeature

        self._ccrs = ccrs
        self._bounds = bounds
        self.selected_points: list[dict] = []
        self._selected: list[dict] = []
        self._existing = list(existing_points or [])

        self.setWindowTitle("")
        self.hideYesButton()
        self.hideCancelButton()
        self.buttonLayout.parent().setVisible(False)
        if hasattr(self, "setClosableOnMaskClicked"):
            self.setClosableOnMaskClicked(False)
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self).activated.connect(self._reject)

        # ── 显示范围（带边距）──
        # [EN] Display extent (with padding)
        lon_range = bounds["lon_max"] - bounds["lon_min"]
        lat_range = bounds["lat_max"] - bounds["lat_min"]
        mlon = max(lon_range * 0.1, 2.0)
        mlat = max(lat_range * 0.1, 2.0)
        self._ext = [
            bounds["lon_min"] - mlon,
            min(bounds["lon_max"] + mlon, 185.0),
            max(bounds["lat_min"] - mlat, -90.0),
            min(bounds["lat_max"] + mlat, 90.0),
        ]

        _configure_cjk_fonts()
        self._fig = Figure(figsize=(10, 8), dpi=100)
        self._canvas = FigureCanvas(self._fig)
        self._canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._ax = self._fig.add_subplot(1, 1, 1, projection=ccrs.PlateCarree(central_longitude=0.5 * (self._ext[0] + self._ext[1])))
        self._ax.set_extent(self._ext, crs=ccrs.PlateCarree())
        try:
            self._ax.add_feature(cfeature.OCEAN, facecolor="#a4d6ff")
            self._ax.add_feature(cfeature.LAND, facecolor="#f0f0f0")
            self._ax.coastlines(resolution="50m", linewidth=0.6)
        except Exception:
            # [EN] Point selection still works when Natural Earth data is missing
            pass  # 自然地球数据缺失时仍可选点
        # 网格范围矩形
        # [EN] Grid bounding rectangle
        bx = [bounds["lon_min"], bounds["lon_max"], bounds["lon_max"], bounds["lon_min"], bounds["lon_min"]]
        by = [bounds["lat_min"], bounds["lat_min"], bounds["lat_max"], bounds["lat_max"], bounds["lat_min"]]
        self._ax.plot(bx, by, transform=ccrs.PlateCarree(), color="blue", linewidth=2, linestyle="--")
        try:
            gl = self._ax.gridlines(draw_labels=True, linewidth=0.5, color="gray", alpha=0.5, linestyle="--")
            gl.top_labels = False
            gl.right_labels = False
        except Exception:
            pass
        self._ax.set_title(tr("step3_select_on_map_subtitle", _TITLE), fontsize=13, fontweight="bold")
        self._fig.subplots_adjust(left=0.04, right=0.99, top=0.94, bottom=0.05)
        self._draw_existing()
        self._canvas.mpl_connect("button_press_event", self._on_click)

        # ── 布局：左画布 + 右按钮 ──
        # [EN] Layout: left canvas + right buttons
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
        delete_last = PrimaryPushButton(tr("step3_delete_last_point", "删除上一个点"))
        delete_last.clicked.connect(self._delete_last)
        for btn in (confirm, cancel, delete_last):
            if button_style:
                btn.setStyleSheet(button_style)
            buttons.addWidget(btn)
        buttons.addStretch(1)
        holder = QWidget()
        holder.setLayout(buttons)
        # 宽度按最宽按钮（"确认并添加点位"）自适应，避免文字被截断。
        # [EN] Width auto-adapts to the widest button ("Confirm and Add Point"),
        # avoiding text truncation.
        width = max(160, confirm.sizeHint().width() + 24)
        holder.setFixedWidth(width)
        row.addWidget(holder, 0)

        self.viewLayout.setContentsMargins(8, 8, 8, 8)
        self.viewLayout.addWidget(content, 1)

    # ── map drawing / interaction ──────────────────────────────────────────

    def _draw_existing(self) -> None:
        ccrs = self._ccrs
        for p in self._existing:
            self._ax.plot(p["lon"], p["lat"], "go", markersize=6, transform=ccrs.PlateCarree())
            self._ax.text(
                p["lon"] + 0.3,
                p["lat"] + 0.3,
                str(p.get("name", "")),
                transform=ccrs.PlateCarree(),
                fontsize=8,
                bbox=dict(boxstyle="round,pad=0.3", facecolor="lightgreen", alpha=0.7),
            )

    def _on_click(self, event) -> None:
        if event.inaxes != self._ax:
            return
        lon, lat = event.xdata, event.ydata
        if lon is None or lat is None or np.isnan(lon) or np.isnan(lat):
            return
        b = self._bounds
        if not (b["lon_min"] <= lon <= b["lon_max"] and b["lat_min"] <= lat <= b["lat_max"]):
            # [EN] Out of bounds, ignore
            return  # 越界忽略
        for p in self._existing + self._selected:
            if abs(p["lon"] - lon) < 1e-3 and abs(p["lat"] - lat) < 1e-3:
                # [EN] Duplicate, ignore
                return  # 重复忽略
        name = str(len(self._existing) + len(self._selected))
        ccrs = self._ccrs
        marker, = self._ax.plot(lon, lat, "ro", markersize=8, transform=ccrs.PlateCarree())
        label = self._ax.text(
            lon + 0.3,
            lat + 0.3,
            name,
            transform=ccrs.PlateCarree(),
            fontsize=9,
            bbox=dict(boxstyle="round,pad=0.3", facecolor="yellow", alpha=0.7),
        )
        self._selected.append({"lon": float(lon), "lat": float(lat), "name": name, "_m": marker, "_t": label})
        self._canvas.draw_idle()

    def _delete_last(self) -> None:
        if not self._selected:
            return
        p = self._selected.pop()
        for key in ("_m", "_t"):
            artist = p.get(key)
            if artist is not None:
                try:
                    artist.remove()
                except Exception:
                    pass
        self._canvas.draw_idle()

    # ── result / close ──────────────────────────────────────────────────────

    def _accept(self) -> None:
        self.selected_points = [
            {"lon": p["lon"], "lat": p["lat"], "name": p["name"]} for p in self._selected
        ]
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
    """复用网格可视化 worker 的 CJK 字体配置，避免标题缺字。

    [EN] Reuse the CJK font configuration from the grid visualization worker
    to avoid missing characters in titles.
    """
    try:
        from workflows.infrastructure.grid_visualization.worker import _configure_matplotlib_cjk_fonts

        _configure_matplotlib_cjk_fonts()
    except Exception:
        pass
