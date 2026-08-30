"""帮助与配置摘要里显示的 params.yml 位置。

0.1.24 起，pip 安装形态下有两个不同的文件：用户的全局配置在用户目录（升级
不动），包内那份是随发行版分发的只读模板（每次升级被替换）。帮助里若只报后
者，用户会去改一个改了也白改的文件。
"""

import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SRC = REPO_ROOT / "src"


def _probe(code, pkg_root, home):
    env = dict(os.environ)
    env.pop("WW3TOOL_PARAMS", None)
    env["PYTHONPATH"] = str(SRC)
    env["WW3TOOL_ROOT"] = str(pkg_root)
    env["HOME"] = str(home)
    env["XDG_CONFIG_HOME"] = str(Path(home) / ".config")
    env["APPDATA"] = str(Path(home) / "AppData" / "Roaming")
    out = subprocess.run([sys.executable, "-c", textwrap.dedent(code)],
                         capture_output=True, text=True, env=env)
    if out.returncode != 0:
        raise AssertionError(out.stderr[-1500:])
    return out.stdout.strip()


class PackagedLayoutPathsTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.home = root / "home"
        self.home.mkdir()
        self.pkg = root / "ww3tool_resources"
        self.pkg.mkdir()
        (self.pkg / "params.yml").write_text("server:\n  host:\n", encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def _locations(self):
        out = _probe("""
            from workflows.interfaces.interactive_cli import _params_locations
            g, t = _params_locations()
            print(g)
            print(t)
        """, self.pkg, self.home)
        g, t = out.splitlines()
        return g, (None if t == "None" else t)

    def test_global_config_is_outside_the_package(self):
        g, _t = self._locations()
        self.assertNotIn("ww3tool_resources", g,
                         "帮助不该把包内模板当成用户配置")
        self.assertTrue(g.startswith(str(self.home)))

    def test_bundled_template_is_reported_separately(self):
        _g, t = self._locations()
        self.assertIsNotNone(t, "pip 形态下应当单独标出只读模板")
        self.assertIn("ww3tool_resources", t)

    def test_the_two_are_different_files(self):
        g, t = self._locations()
        self.assertNotEqual(g, t)


class RepoLayoutPathsTest(unittest.TestCase):
    """仓库形态下二者本就是同一个文件，不该多显示一行。"""

    @unittest.skipUnless((REPO_ROOT / "run.py").is_file(), "需要仓库形态")
    def test_only_one_location_is_reported(self):
        sys.path.insert(0, str(SRC))
        from workflows.interfaces.interactive_cli import _params_locations
        g, t = _params_locations()
        self.assertIsNone(t)
        self.assertTrue(g.endswith("params.yml"))


class HelpTextTest(unittest.TestCase):
    @unittest.skipUnless((REPO_ROOT / "run.py").is_file(), "需要仓库形态")
    def test_help_mentions_where_settings_live(self):
        out = subprocess.run([sys.executable, str(REPO_ROOT / "run.py"), "--help"],
                             capture_output=True, text=True, cwd=str(REPO_ROOT))
        text = out.stdout
        self.assertIn("params.yml", text)
        # 顺带告诉用户算例参数从哪来
        self.assertIn("workdir", text)


if __name__ == "__main__":
    unittest.main()
