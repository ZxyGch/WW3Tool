"""地图资源打包、按需请求和桌面底图切换回归。"""

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
ASSETS = ROOT / "public" / "globe_picker"


class MapLoadingTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "JavaScript 回归需要 Node.js")
    def test_style_loader(self):
        result = subprocess.run(
            [shutil.which("node"), "--test", str(Path(__file__).with_name("map_style_loader.test.cjs"))],
            capture_output=True, text=True, timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_local_engine_is_in_packaged_resources(self):
        # 运行实际资源复制逻辑，确认体积限制不会漏掉地图引擎。
        import importlib.util

        spec = importlib.util.spec_from_file_location("map_packaging_run", ROOT / "run.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            module._BUILD_STAGE = Path(directory)
            module._build_walk_copy(ROOT, "public/globe_picker")
            for name in ["maplibre-gl.js", "maplibre-gl.css", "LICENSE.txt"]:
                relative = Path("vendor/maplibre-gl-4.7.1") / name
                bundled = Path(directory) / "public/globe_picker" / relative
                self.assertEqual(bundled.read_bytes(), (ASSETS / relative).read_bytes())
            self.assertTrue((Path(directory) / "public/globe_picker/map_style_loader.js").is_file())

    def test_desktop_map_without_network(self):
        # 独立进程隔离 QApplication 和 WebEngine 图形上下文。
        try:
            import PyQt6.QtWebEngineCore  # noqa: F401
            import qframelesswindow  # noqa: F401
        except ImportError:
            self.skipTest("桌面地图回归需要 QtWebEngine 和 qframelesswindow")
        env = dict(os.environ, PYTHONPATH=str(ROOT / "src"), QT_QPA_PLATFORM="offscreen")
        env["QTWEBENGINE_CHROMIUM_FLAGS"] = (
            "--no-sandbox --use-gl=angle --use-angle=swiftshader "
            "--enable-unsafe-swiftshader --disable-gpu-compositing"
        )
        # 等 WebEngine 进程退出后再回收缓存目录，避免后台写入和清理竞争。
        with tempfile.TemporaryDirectory() as cache_dir:
            env["WW3TOOL_MAP_TEST_CACHE"] = cache_dir
            result = subprocess.run(
                [sys.executable, str(Path(__file__).with_name("map_loading_smoke.py"))],
                cwd=ROOT, env=env, capture_output=True, text=True, timeout=35,
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
