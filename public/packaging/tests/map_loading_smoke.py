"""在独立 QtWebEngine 进程中验证本地地图启动和底图切换。"""

import json
import os
from pathlib import Path
from unittest.mock import patch

from PyQt6.QtCore import QCoreApplication, QEvent, QEventLoop, QTimer, QUrl, Qt

QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)

from PyQt6.QtWidgets import QApplication
from PyQt6.QtWebEngineCore import QWebEngineProfile, QWebEngineSettings, QWebEngineUrlRequestInterceptor
from desktop.components import globe_picker_dialog as picker
from desktop.components.bounds_map_preview import BoundsMapPreview

app = QApplication(["ww3tool-map-smoke"])


class BlockNetwork(QWebEngineUrlRequestInterceptor):
    def __init__(self, parent):
        super().__init__(parent)
        self.requests = []

    def interceptRequest(self, info):
        url = info.requestUrl().toString()
        if url.startswith(("http:", "https:")):
            self.requests.append(url)
            info.block(True)


def evaluate(page, code):
    loop = QEventLoop()
    result = []

    def done(value):
        result.append(value)
        loop.quit()

    page.runJavaScript(code, done)
    QTimer.singleShot(2000, loop.quit)
    loop.exec()
    assert result, "JavaScript 调用超时"
    return result[0]


def wait_until(page, condition):
    loop = QEventLoop()
    timer = QTimer()
    timer.setInterval(50)
    timer.timeout.connect(lambda: page.runJavaScript(condition, lambda ok: loop.quit() if ok else None))
    timer.start()
    QTimer.singleShot(7000, loop.quit)
    loop.exec()
    timer.stop()
    assert evaluate(page, condition), evaluate(page, "document.getElementById('toolbar-status').textContent")


def check_maps(cache_dir):
    with patch.object(picker.QStandardPaths, "writableLocation", return_value=cache_dir):
        view = picker.MapWebEngineView()
        second_view = picker.MapWebEngineView()
    page = view.page()
    profile = page.profile()
    assert profile is second_view.page().profile()
    assert not profile.isOffTheRecord()
    assert profile.httpCacheType() == QWebEngineProfile.HttpCacheType.DiskHttpCache
    assert profile.httpCacheMaximumSize() == 256 * 1024 * 1024
    assert profile.cachePath().startswith(cache_dir)
    blocker = BlockNetwork(profile)
    profile.setUrlRequestInterceptor(blocker)
    page.settings().setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
    page.settings().setAttribute(QWebEngineSettings.WebAttribute.WebGLEnabled, True)
    view.resize(900, 500)
    asset = Path("public/globe_picker/globe_picker.html").resolve()
    # 暴露测试观测点；生产页面保持封装。
    html = asset.read_text().replace(
        "var map = new maplibregl.Map({", "var map = window.__testMap = new maplibregl.Map({"
    )
    html = html.replace(
        "createMapStyleLoader(RASTER_STYLES, optimizeAdministrativeStyle)",
        "createMapStyleLoader(RASTER_STYLES, optimizeAdministrativeStyle, 100)"
    )
    ready = "Boolean(window.__testMap && __testMap.getSource('draw-rect'))"
    region = {"west": 110, "east": 130, "south": 10, "north": 35}
    data = "__testMap.getSource('draw-rect')._data"

    for map_type in ["satellite", "administrative", "dark", "light"]:
        blocker.requests.clear()
        case = html.replace(
            "new URLSearchParams(window.location.search)",
            "new URLSearchParams('?mode=preview&lang=zh&mapType=" + map_type + "')"
        )
        view.setHtml(case, QUrl.fromLocalFile(str(asset)))
        view.show()
        wait_until(page, ready)
        if map_type != "administrative":
            assert not any("openfreemap" in url or "unpkg" in url for url in blocker.requests)
        else:
            assert evaluate(page, "!document.getElementById('map-fallback').hidden")
            assert evaluate(page, "__testMap.getStyle().sources['base-tiles'].tiles[0].includes('light_all')")
        assert evaluate(page, "window.__setPreviewRegions(" + json.dumps([region]) + ")")
        original_data = evaluate(page, data)
        evaluate(page, "window.__savedMap=__testMap; true")

        # 通过真实 Python 回调切换底图，证明没有导航或区域丢失。
        class Host:
            _page_loaded = True

            def page(self):
                return page

        with patch("desktop.components.bounds_map_preview.current_map_type", return_value="dark"):
            BoundsMapPreview.reload_map_type(Host())
        wait_until(page, ready + " && __testMap.getStyle().sources['base-tiles'].tiles[0].includes('dark_all')")
        assert evaluate(page, "__savedMap === __testMap")
        assert evaluate(page, data) == original_data

        # 慢请求返回后不能覆盖用户随后选择的底图。
        evaluate(page, "window.fetch=()=>new Promise(()=>{}); __setMapType('administrative'); __setMapType('light'); true")
        wait_until(page, ready + " && __testMap.getStyle().sources['base-tiles'].tiles[0].includes('light_all')")
        loop = QEventLoop()
        QTimer.singleShot(180, loop.quit)
        loop.exec()
        assert evaluate(page, "document.getElementById('map-fallback').hidden")
        assert evaluate(page, "document.getElementById('style-select-label').textContent") == "亮色图"
        assert evaluate(page, data) == original_data

    view.deleteLater()
    second_view.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    profile.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
check_maps(os.environ["WW3TOOL_MAP_TEST_CACHE"])
print("4 种底图启动、缓存设置、区域保留与快速切换通过")
