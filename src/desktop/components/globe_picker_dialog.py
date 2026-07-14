"""3D 地球矩形区域选择对话框。

使用 MapLibre GL JS 在 QWebEngineView 中渲染 3D 地球，
用户拖拽绘制矩形选框，确认后通过 JavaScript 回调回传经纬度坐标。
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QTimer, QUrl
from PyQt6.QtWebEngineCore import QWebEngineSettings
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QDialog, QVBoxLayout

from workflows.support.translations import tr


class GlobePickerDialog(QDialog):
    """在 3D 地球上手绘矩形、取回经纬度范围的对话框。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._bounds: tuple[float, float, float, float] | None = None

        self.setWindowTitle(tr("globe_picker_title", "3D 地球 - 选择矩形区域"))
        self.setMinimumSize(1000, 700)
        self.resize(1200, 800)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._webview = QWebEngineView()
        layout.addWidget(self._webview)

        # WebEngine 设置
        page = self._webview.page()
        settings = page.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.WebGLEnabled, True)
        for attribute_name in ("Accelerated2dCanvasEnabled", "AutoLoadImages"):
            attribute = getattr(QWebEngineSettings.WebAttribute, attribute_name, None)
            if attribute is not None:
                settings.setAttribute(attribute, True)

        # 页面加载完成后注入确认按钮的监听
        page.loadFinished.connect(self._on_page_loaded)

        # 加载 HTML
        html_path = Path(__file__).parent.parent.parent.parent / "public" / "globe_picker" / "globe_picker.html"
        self._webview.load(QUrl.fromLocalFile(str(html_path.resolve())))

        # 定时检查 JS 端是否有确认结果
        self._check_timer = QTimer(self)
        self._check_timer.timeout.connect(self._poll_result)
        self._check_timer.setInterval(200)

    def _on_page_loaded(self, ok: bool) -> None:
        if not ok:
            self.setWindowTitle(
                tr("globe_picker_title", "3D 地球 - 选择矩形区域") + " - 地图加载失败"
            )
            return
        self._check_timer.start()

    def _poll_result(self) -> None:
        self._webview.page().runJavaScript(
            "window.__globeResult || null",
            self._on_js_result,
        )

    def _on_js_result(self, result: object) -> None:
        if result is None:
            return
        if not isinstance(result, dict):
            return
        try:
            west = float(result["west"])
            east = float(result["east"])
            south = float(result["south"])
            north = float(result["north"])
        except (KeyError, TypeError, ValueError):
            return
        self._check_timer.stop()
        self._bounds = (west, east, south, north)
        self.accept()

    def get_bounds(self) -> tuple[float, float, float, float] | None:
        """返回用户选择的矩形范围 (west, east, south, north)，取消返回 None。"""
        return self._bounds
