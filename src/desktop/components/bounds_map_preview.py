"""Reusable inline map preview for editable geographic bounds."""

from __future__ import annotations

import json
import math
from pathlib import Path

from PyQt6.QtCore import QRectF, QTimer, QUrl, QUrlQuery
from PyQt6.QtGui import QColor, QPainterPath, QRegion
from PyQt6.QtWebEngineCore import QWebEngineSettings
from PyQt6.QtWidgets import QSizePolicy

from .globe_picker_dialog import MapWebEngineView, current_map_language


class BoundsMapPreview(MapWebEngineView):
    """Show a blue outline for four bound fields without map editing controls."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._page_loaded = False
        self._regions: list[dict[str, object]] = []
        self._field_regions: list[dict[str, object]] = []
        self._field_connections: list[tuple[object, object]] = []
        self._update_timer = QTimer(self)
        self._update_timer.setSingleShot(True)
        self._update_timer.setInterval(180)
        self._update_timer.timeout.connect(self._update_from_bound_fields)

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

    def bind_fields(
        self, *, west, east, south, north, color: str = "#1677d2", label: str = ""
    ) -> None:
        self._clear_field_bindings()
        self.add_bound_fields(
            west=west, east=east, south=south, north=north, color=color, label=label
        )

    def add_bound_fields(
        self, *, west, east, south, north, color: str = "#1677d2", label: str = ""
    ) -> None:
        fields = (west, east, south, north)
        self._field_regions.append({"fields": fields, "color": color, "label": label})
        for field in fields:
            slot = lambda *_: self._update_timer.start()
            field.textChanged.connect(slot)
            self._field_connections.append((field, slot))
        self._update_timer.start()

    def replace_bound_fields(self, bindings: list[dict[str, object]]) -> None:
        """Replace all live field bindings, for example after nested levels change."""
        self._clear_field_bindings()
        for binding in bindings:
            self.add_bound_fields(**binding)
        if not bindings:
            self.clear_bounds()

    def _clear_field_bindings(self) -> None:
        self._update_timer.stop()
        for field, slot in self._field_connections:
            try:
                field.textChanged.disconnect(slot)
            except (RuntimeError, TypeError):
                pass
        self._field_connections.clear()
        self._field_regions.clear()

    def set_bounds(self, west: float, east: float, south: float, north: float) -> None:
        self.set_regions([{"west": west, "east": east, "south": south, "north": north}])

    def set_regions(self, regions: list[dict[str, object]]) -> None:
        self._regions = [dict(region) for region in regions]
        self._sync_regions()

    def clear_bounds(self) -> None:
        self.set_regions([])

    def refresh(self) -> None:
        self._update_timer.stop()
        self._update_from_bound_fields()

    def regions(self) -> list[dict[str, object]]:
        return [dict(region) for region in self._regions]

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
            self._sync_regions()
            self._restore_host_frameless()
            QTimer.singleShot(0, self._restore_host_frameless)
            QTimer.singleShot(100, self._restore_host_frameless)

    def _update_from_bound_fields(self) -> None:
        if not self._field_regions:
            return
        regions: list[dict[str, object]] = []
        for binding in self._field_regions:
            fields = binding["fields"]
            try:
                west, east, south, north = (
                    float(field.text().strip()) for field in fields
                )
            except ValueError:
                continue
            if not all(math.isfinite(value) for value in (west, east, south, north)):
                continue
            while east <= west:
                east += 360
            if south >= north or south < -90 or north > 90 or east - west > 360:
                continue
            regions.append(
                {
                    "west": west,
                    "east": east,
                    "south": south,
                    "north": north,
                    "color": binding["color"],
                    "label": binding["label"],
                    "width": 1.5,
                }
            )
        self.set_regions(regions)

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

    def _sync_regions(self) -> None:
        if not self._page_loaded:
            return
        payload = json.dumps(self._regions, separators=(",", ":"))
        self.page().runJavaScript(f"window.__setPreviewRegions({payload})")
