"""Embedded 3D globe rectangle picker.

The picker is a child overlay of the main window instead of a top-level dialog.
This avoids native title-bar and compositor conflicts between macOS and QWebEngineView.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QEvent, QEventLoop, Qt, QTimer, QUrl
from PyQt6.QtGui import QColor
from PyQt6.QtWebEngineCore import QWebEngineSettings
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from qframelesswindow.webengine import FramelessWebEngineView


class GlobePickerDialog(QWidget):
    """Display the globe as a modal-looking card embedded in the main window."""

    DialogCode = QDialog.DialogCode

    def __init__(self, parent=None):
        host = parent or QApplication.activeWindow()
        if host is None:
            raise RuntimeError("3D 地球选择器需要主窗口作为父组件")
        super().__init__(host)

        self._bounds: tuple[float, float, float, float] | None = None
        self._result = self.DialogCode.Rejected
        self._event_loop: QEventLoop | None = None

        self.setObjectName("globePickerOverlay")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        dark = host.palette().color(host.palette().ColorRole.Window).lightness() < 128
        card_color = "#202020" if dark else "#ffffff"
        self.setStyleSheet(
            "QWidget#globePickerOverlay { background-color: rgba(0, 0, 0, 76); }"
            f"QFrame#globePickerCard {{ background-color: {card_color}; border-radius: 8px; }}"
        )

        overlay_layout = QHBoxLayout(self)
        overlay_layout.setContentsMargins(0, 0, 0, 0)
        self._card = QFrame(self, objectName="globePickerCard")
        overlay_layout.addWidget(self._card, 0, Qt.AlignmentFlag.AlignCenter)

        card_layout = QVBoxLayout(self._card)
        card_layout.setContentsMargins(8, 8, 8, 8)
        card_layout.setSpacing(0)

        # qframelesswindow 会在 WebEngine 创建原生视图后重新应用 macOS 无边框状态。
        self._webview = FramelessWebEngineView(self._card)
        self._webview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._webview.setMinimumSize(320, 240)
        self._webview.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self._webview.page().setBackgroundColor(QColor("#d7e9f5"))
        card_layout.addWidget(self._webview, 1)

        page = self._webview.page()
        settings = page.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.WebGLEnabled, True)
        for attribute_name in ("Accelerated2dCanvasEnabled", "AutoLoadImages"):
            attribute = getattr(QWebEngineSettings.WebAttribute, attribute_name, None)
            if attribute is not None:
                settings.setAttribute(attribute, True)
        page.loadFinished.connect(self._on_page_loaded)

        html_path = Path(__file__).parent.parent.parent.parent / "public" / "globe_picker" / "globe_picker.html"
        self._webview.load(QUrl.fromLocalFile(str(html_path.resolve())))

        self._check_timer = QTimer(self)
        self._check_timer.timeout.connect(self._poll_result)
        self._check_timer.setInterval(200)

        host.installEventFilter(self)
        self.hide()

    def exec(self) -> QDialog.DialogCode:
        """Run a local event loop while keeping the picker inside the main window."""
        self._result = self.DialogCode.Rejected
        self._restore_host_frameless()
        self._sync_to_host()
        self.show()
        self.raise_()
        self.setFocus(Qt.FocusReason.ActiveWindowFocusReason)

        self._event_loop = QEventLoop(self)
        self._event_loop.exec()
        self._event_loop = None
        result = self._result
        QTimer.singleShot(0, self.deleteLater)
        return result

    def accept(self) -> None:
        self._finish(self.DialogCode.Accepted)

    def reject(self) -> None:
        self._finish(self.DialogCode.Rejected)

    def _finish(self, result: QDialog.DialogCode) -> None:
        self._result = result
        self._check_timer.stop()
        self.hide()
        self._restore_host_frameless()
        QTimer.singleShot(0, self._restore_host_frameless)
        if self._event_loop is not None and self._event_loop.isRunning():
            self._event_loop.quit()

    def _restore_host_frameless(self) -> None:
        host = self.parentWidget()
        if host is None:
            return
        update_frameless = getattr(host, "updateFrameless", None)
        if callable(update_frameless):
            update_frameless()
        set_system_buttons = getattr(host, "setSystemTitleBarButtonVisible", None)
        if callable(set_system_buttons):
            set_system_buttons(False)
        if self.isVisible():
            self.raise_()
        else:
            title_bar = getattr(host, "titleBar", None)
            if title_bar is not None:
                title_bar.raise_()

    def _sync_to_host(self) -> None:
        host = self.parentWidget()
        if host is None:
            return
        self.setGeometry(host.rect())
        card_width = max(320, min(1800, int(host.width() * 0.90)))
        card_height = max(240, min(1080, int(host.height() * 0.86)))
        self._card.setFixedSize(card_width, card_height)

    def eventFilter(self, watched, event) -> bool:
        if watched is self.parentWidget() and event.type() in {
            QEvent.Type.Resize,
            QEvent.Type.Show,
        }:
            self._sync_to_host()
            if self.isVisible():
                QTimer.singleShot(0, self.raise_)
        return super().eventFilter(watched, event)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._sync_to_host()
        QTimer.singleShot(0, self.raise_)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if (
            event.button() == Qt.MouseButton.LeftButton
            and not self._card.geometry().contains(event.position().toPoint())
        ):
            self.reject()
            return
        super().mouseReleaseEvent(event)

    def _on_page_loaded(self, ok: bool) -> None:
        if ok:
            self._restore_host_frameless()
            QTimer.singleShot(0, self._restore_host_frameless)
            self._check_timer.start()

    def _poll_result(self) -> None:
        self._webview.page().runJavaScript(
            "window.__globeResult || null",
            self._on_js_result,
        )

    def _on_js_result(self, result: object) -> None:
        if not isinstance(result, dict):
            return
        try:
            west = float(result["west"])
            east = float(result["east"])
            south = float(result["south"])
            north = float(result["north"])
        except (KeyError, TypeError, ValueError):
            return
        self._bounds = (west, east, south, north)
        self.accept()

    def get_bounds(self) -> tuple[float, float, float, float] | None:
        """Return selected bounds as ``(west, east, south, north)``."""
        return self._bounds
