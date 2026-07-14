"""Region map loading + display dialog for Step 1 "查看地图".

Uses qfluentwidgets MessageBoxBase so the platform-level compositing (semi-transparent
overlay, click-outside-to-close, rounded card) is handled by qfluentwidgets itself.

[EN] Region map loading + display dialog for Step 1 "View Map".

Uses qfluentwidgets MessageBoxBase so the platform-level compositing (semi-transparent
overlay, click-outside-to-close, rounded card) is handled by qfluentwidgets itself.

Sizing strategy
---------------
1. In showEvent, post a single QTimer shot that sets card.setFixedSize(dw, dh) once
   the Qt layout has processed the initial show.
2. Never call setFixedSize again after the card is sized — the layout engine then
   naturally fills stack → _image_host → _ScaledMapLabel top-to-bottom.
3. _ScaledMapLabel.resizeEvent fires when Qt assigns it its final size, which calls
   _apply_scale with the correct contentsRect().
"""

from __future__ import annotations

import numpy as np
from PyQt6 import QtCore
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeySequence, QPixmap, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QLabel,
    QProgressBar,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import MessageBoxBase
from workflows.support.translations import tr


class _ScaledMapLabel(QLabel):
    """Scales a high-res pixmap to fill the available area while keeping aspect ratio."""

    def __init__(self, full_pixmap: QPixmap, parent=None):
        super().__init__(parent)
        self._full = full_pixmap
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(1, 1)
        self.setScaledContents(False)

    def sizeHint(self):
        return QtCore.QSize(320, 240)

    def minimumSizeHint(self):
        return QtCore.QSize(1, 1)

    def _device_pixel_ratio(self) -> float:
        wh = self.window().windowHandle()
        if wh is not None:
            return float(wh.devicePixelRatio())
        scr = self.screen()
        if scr is not None:
            return float(scr.devicePixelRatio())
        return 1.0

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_scale()

    def showEvent(self, event):
        super().showEvent(event)
        QtCore.QTimer.singleShot(0, self._apply_scale)

    def _apply_scale(self):
        if self._full is None or self._full.isNull():
            return
        r = self.contentsRect()
        if r.width() < 2 or r.height() < 2:
            return
        dpr = max(1.0, self._device_pixel_ratio())
        tw = max(2, int(round(r.width() * dpr)))
        th = max(2, int(round(r.height() * dpr)))
        scaled = self._full.scaled(
            QtCore.QSize(tw, th),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        scaled.setDevicePixelRatio(dpr)
        QLabel.setPixmap(self, scaled)


class RegionMapDialog(MessageBoxBase):
    """Region map dialog: loading page → map image page.

    MessageBoxBase provides:
    - Platform-composited semi-transparent overlay
    - Rounded card matching the app's fluent design
    - Click-outside-card-to-close via setClosableOnMaskClicked
    """

    def __init__(self, parent=None, *, map_aspect_wh: float | None = None):
        super().__init__(parent)
        self.setWindowTitle("")
        self._map_aspect_wh = float(map_aspect_wh) if map_aspect_wh and map_aspect_wh > 0 else 4.0 / 3.0
        self._cancel_cb = None

        # Hide default buttons; remove the button bar entirely
        self.hideYesButton()
        self.hideCancelButton()
        self.buttonLayout.parent().setVisible(False)

        # Click outside the card closes the dialog
        if hasattr(self, "setClosableOnMaskClicked"):
            self.setClosableOnMaskClicked(True)

        # Stack: page 0 = loading, page 1 = map image
        self._stack = QStackedWidget()
        self._stack.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._stack.setMinimumSize(320, 240)

        # Page 0: loading
        loading_w = QWidget()
        loading_layout = QVBoxLayout(loading_w)
        loading_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._loading_label = QLabel(tr("step1_generating_map", "正在生成地图..."))
        self._loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._loading_label.setWordWrap(True)
        loading_layout.addWidget(self._loading_label)
        self._loading_bar = QProgressBar()
        self._loading_bar.setRange(0, 0)
        self._loading_bar.setFixedWidth(280)
        loading_layout.addWidget(self._loading_bar, alignment=Qt.AlignmentFlag.AlignCenter)
        self._stack.addWidget(loading_w)

        # Page 1: map image (populated by show_image)
        self._image_host = QWidget()
        self._image_host.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._image_layout = QVBoxLayout(self._image_host)
        self._image_layout.setContentsMargins(0, 0, 0, 0)
        self._image_layout.setSpacing(0)
        self._stack.addWidget(self._image_host)
        self._stack.setCurrentIndex(0)

        # Keep an 8 px inset so the map image doesn't bleed past the card's rounded corners
        self.viewLayout.setContentsMargins(8, 8, 8, 8)
        self.viewLayout.setSpacing(0)
        self.viewLayout.addWidget(self._stack, 1)

        esc = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        esc.activated.connect(self._close_dialog)

    def set_cancel_callback(self, cb) -> None:
        self._cancel_cb = cb

    # ── public API ────────────────────────────────────────────────────────────

    def show_image(self, png_path: str) -> None:
        """Switch from loading to map image. Call from the on_done callback."""
        pm = QPixmap(png_path)
        if pm.isNull():
            self.show_error(tr("step1_map_image_load_failed", "无法加载地图图片"))
            return
        while self._image_layout.count():
            item = self._image_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        map_label = _ScaledMapLabel(pm)
        self._image_layout.addWidget(map_label, 1)
        self._stack.setCurrentIndex(1)
        # Let Qt settle the layout, then re-scale
        QtCore.QTimer.singleShot(0, map_label._apply_scale)
        QtCore.QTimer.singleShot(50, map_label._apply_scale)

    def show_error(self, message: str) -> None:
        self._loading_label.setText(tr("step1_map_generation_failed", "地图生成失败：{message}").format(message=message))
        self._loading_bar.setVisible(False)

    # ── sizing ────────────────────────────────────────────────────────────────

    def showEvent(self, event):
        super().showEvent(event)
        # Post a single sizing call so Qt has processed the initial layout first
        QtCore.QTimer.singleShot(0, self._size_card_once)

    def _avail_rect(self):
        parent = self.parentWidget()
        if parent is not None and parent.isVisible():
            r = parent.frameGeometry()
            return int(r.width() * 0.90), int(r.height() * 0.84)
        screen = QApplication.primaryScreen()
        ag = screen.availableGeometry() if screen else None
        if ag:
            return int(ag.width() * 0.88), int(ag.height() * 0.82)
        return 1000, 760

    def _size_card_once(self):
        """Set card size based on map aspect ratio — called exactly once after show."""
        card = getattr(self, "widget", None)
        if card is None:
            return
        avail_w, avail_h = self._avail_rect()
        a = float(np.clip(self._map_aspect_wh, 0.2, 14.0))
        if avail_w / max(avail_h, 1) > a:
            dh = avail_h
            dw = int(round(dh * a))
        else:
            dw = avail_w
            dh = int(round(dw / a))
        dw = max(400, min(dw, 1920))
        dh = max(300, min(dh, 1080))
        card.setFixedSize(dw, dh)

    # ── close ─────────────────────────────────────────────────────────────────

    def reject(self):
        self._fire_cancel()
        QDialog.done(self, int(QDialog.DialogCode.Rejected))

    def _close_dialog(self):
        self._fire_cancel()
        QDialog.done(self, int(QDialog.DialogCode.Accepted))

    def closeEvent(self, event):
        self._fire_cancel()
        super().closeEvent(event)

    def _fire_cancel(self):
        cb = self._cancel_cb
        self._cancel_cb = None
        if callable(cb):
            cb()
