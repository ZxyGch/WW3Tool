"""Inline map preview for the level-0 grid bounds."""

from __future__ import annotations

import json
from pathlib import Path

from PyQt6.QtCore import QRectF, QTimer, QUrl, QUrlQuery
from PyQt6.QtGui import QColor, QPainterPath, QRegion
from PyQt6.QtWebEngineCore import QWebEngineSettings
from PyQt6.QtWidgets import QSizePolicy

from .globe_picker_dialog import MapWebEngineView, current_map_language


class GridBoundsPreview(MapWebEngineView):
    """Show the current grid extent without exposing map editing controls."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._page_loaded = False
        self._bounds: dict[str, float] | None = None

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(210)
        self.setZoomFactor(1.0)
        page = self.page()
        page.setBackgroundColor(QColor("#ffffff"))
        settings = page.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.WebGLEnabled, True)
        page.loadFinished.connect(self._on_page_loaded)

        html_path = Path(__file__).parents[3] / "public" / "globe_picker" / "globe_picker.html"
        url = QUrl.fromLocalFile(str(html_path.resolve()))
        query = QUrlQuery()
        query.addQueryItem("mode", "preview")
        query.addQueryItem("lang", current_map_language())
        url.setQuery(query)
        self.load(url)

    def set_bounds(self, west: float, east: float, south: float, north: float) -> None:
        self._bounds = {
            "west": west,
            "east": east,
            "south": south,
            "north": north,
        }
        self._sync_bounds()

    def clear_bounds(self) -> None:
        self._bounds = None
        self._sync_bounds()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), 8.0, 8.0)
        self.setMask(QRegion(path.toFillPolygon().toPolygon()))

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._restore_host_frameless()

    def _on_page_loaded(self, ok: bool) -> None:
        self._page_loaded = ok
        if ok:
            self._sync_bounds()
            self._restore_host_frameless()
            QTimer.singleShot(0, self._restore_host_frameless)
            QTimer.singleShot(100, self._restore_host_frameless)

    def _restore_host_frameless(self) -> None:
        host = self.window()
        if host is self:
            return
        update_frameless = getattr(host, "updateFrameless", None)
        if callable(update_frameless):
            update_frameless()
        set_system_buttons = getattr(host, "setSystemTitleBarButtonVisible", None)
        if callable(set_system_buttons):
            set_system_buttons(False)
        title_bar = getattr(host, "titleBar", None)
        if title_bar is not None:
            title_bar.raise_()

    def _sync_bounds(self) -> None:
        if not self._page_loaded:
            return
        payload = json.dumps(self._bounds, separators=(",", ":"))
        self.page().runJavaScript(f"window.__setPreviewBounds({payload})")
