"""发布卫生：模板不得携带开发者信息；无头环境不该被 GUI 依赖挡住。"""

import importlib.util
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[3]


def _load_run():
    spec = importlib.util.spec_from_file_location("ww3run_under_test", REPO_ROOT / "run.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ww3run_under_test"] = mod
    spec.loader.exec_module(mod)
    return mod


@unittest.skipUnless((REPO_ROOT / "run.py").is_file(), "仓库形态才有 run.py")
class TemplateSanitizerTest(unittest.TestCase):
    """params.yml 既是开发者日常配置又随包分发，打包前必须去个人化。"""

    @classmethod
    def setUpClass(cls):
        cls.runmod = _load_run()

    def test_home_paths_are_blanked(self):
        src = ("workdir:\n"
               "  path: /Users/someone/proj/workSpace\n"
               "  default_workspace: /home/someone/ws\n")
        out = self.runmod._sanitize_params_template(src)
        self.assertNotIn("/Users/", out)
        self.assertNotIn("/home/someone", out)
        self.assertIn("path:", out)          # 键保留

    def test_cluster_home_paths_are_blanked(self):
        out = self.runmod._sanitize_params_template("  exe: /public/home/abc123/bin/ww3\n")
        self.assertNotIn("/public/home/", out)

    def test_machine_identity_keys_are_blanked(self):
        src = ("server:\n"
               "  ssh_config_host: MY-CLUSTER\n"
               "  default_remote_dir: /public/home/abc/work\n"
               "  user: abc123\n"
               "  port: 22\n")
        out = self.runmod._sanitize_params_template(src)
        self.assertNotIn("MY-CLUSTER", out)
        self.assertNotIn("abc123", out)
        self.assertIn("port: 22", out)       # 非个人设置保持原样

    def test_history_lists_are_emptied(self):
        src = ("desktop:\n"
               "  recent_workdirs:\n"
               "  - /Users/someone/a\n"
               "  - /Users/someone/b\n"
               "  theme: dark\n")
        out = self.runmod._sanitize_params_template(src)
        self.assertIn("recent_workdirs: []", out)
        self.assertNotIn("/Users/", out)
        self.assertIn("theme: dark", out)

    def test_comments_survive(self):
        src = ("# 这一行说明很重要\n"
               "workdir:\n"
               "  path: /Users/someone/x   # 行尾注释\n")
        out = self.runmod._sanitize_params_template(src)
        self.assertIn("# 这一行说明很重要", out)

    def test_relative_and_neutral_values_untouched(self):
        src = ("grid:\n"
               "  reference_data_path: ./meshgen/reference_data\n"
               "  dx: 0.5\n")
        self.assertEqual(self.runmod._sanitize_params_template(src), src)

    def test_namelist_values_are_blanked(self):
        src = "&GRID_INIT\n  REF_DIR = '/Users/someone/refdata'\n  FNAME = 'grid'\n/\n"
        out = self.runmod._sanitize_config_text(src)
        self.assertNotIn("/Users/", out)
        self.assertIn("REF_DIR = ''", out)
        self.assertIn("FNAME = 'grid'", out)

    def test_the_real_template_comes_out_clean(self):
        template = REPO_ROOT / "params.yml"
        if not template.is_file():
            self.skipTest("仓库根没有 params.yml")
        out = self.runmod._sanitize_params_template(template.read_text(encoding="utf-8"))
        for marker in ("/Users/", "/root/", "/public/home/"):
            self.assertNotIn(marker, out, msg=f"模板里仍残留 {marker}")
        import yaml
        self.assertIsInstance(yaml.safe_load(out), dict)


@unittest.skipUnless((REPO_ROOT / "run.py").is_file(), "仓库形态才有 run.py")
class HeadlessFallbackTest(unittest.TestCase):
    """无头机器上不该为了一个开不出来的窗口去装 GUI 依赖。"""

    @classmethod
    def setUpClass(cls):
        cls.runmod = _load_run()

    def test_macos_and_windows_always_have_a_desktop(self):
        for plat in ("darwin", "win32"):
            with mock.patch.object(sys, "platform", plat), \
                 mock.patch.dict(os.environ, {}, clear=True):
                self.assertTrue(self.runmod._has_desktop_environment())

    def test_linux_without_a_display_is_headless(self):
        with mock.patch.object(sys, "platform", "linux"), \
             mock.patch.dict(os.environ, {}, clear=True):
            self.assertFalse(self.runmod._has_desktop_environment())

    def test_linux_with_x11_or_wayland_has_a_desktop(self):
        for var in ("DISPLAY", "WAYLAND_DISPLAY"):
            with mock.patch.object(sys, "platform", "linux"), \
                 mock.patch.dict(os.environ, {var: ":0"}, clear=True):
                self.assertTrue(self.runmod._has_desktop_environment(), msg=var)

    def test_empty_display_still_counts_as_headless(self):
        with mock.patch.object(sys, "platform", "linux"), \
             mock.patch.dict(os.environ, {"DISPLAY": "  "}, clear=True):
            self.assertFalse(self.runmod._has_desktop_environment())

    def test_force_override_wins(self):
        with mock.patch.object(sys, "platform", "linux"), \
             mock.patch.dict(os.environ, {"WW3TOOL_FORCE_DESKTOP": "1"}, clear=True):
            self.assertTrue(self.runmod._has_desktop_environment())

    def test_force_override_off_is_ignored(self):
        with mock.patch.object(sys, "platform", "linux"), \
             mock.patch.dict(os.environ, {"WW3TOOL_FORCE_DESKTOP": "0"}, clear=True):
            self.assertFalse(self.runmod._has_desktop_environment())

    def test_desktop_mode_only_asks_for_gui_packages(self):
        # 有桌面的环境仍要检查 GUI 包——不该跳过。
        self.assertGreater(len(self.runmod._required_imports("desktop")),
                           len(self.runmod._required_imports("shell")))


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless((REPO_ROOT / "run.py").is_file(), "仓库形态才有 run.py")
class EntryPointRoutingTest(unittest.TestCase):
    """入口约定：裸 ww3tool 只给帮助，桌面端要显式 --gui。"""

    @classmethod
    def setUpClass(cls):
        cls.runmod = _load_run()

    def _main(self, argv):
        """跑 main()，把帮助与桌面端两个出口都换成探针。"""
        calls = {"help": 0, "desktop": 0, "shell": 0}

        import types
        icli = types.ModuleType("workflows.interfaces.interactive_cli")
        icli.print_help = lambda: calls.__setitem__("help", calls["help"] + 1)
        icli.main = lambda *a, **k: calls.__setitem__("shell", calls["shell"] + 1) or 0
        app = types.ModuleType("desktop.application")
        app.main = lambda *a, **k: calls.__setitem__("desktop", calls["desktop"] + 1) or 0

        with mock.patch.dict(sys.modules, {
            "workflows.interfaces.interactive_cli": icli,
            "desktop.application": app,
        }), mock.patch.object(self.runmod, "_bootstrap_src_imports", lambda: None), \
             mock.patch.object(self.runmod, "_ensure_runtime", lambda **k: None):
            code = self.runmod.main(argv)
        return code, calls

    def test_bare_command_prints_help(self):
        code, calls = self._main([])
        self.assertEqual(code, 0)
        self.assertEqual(calls["help"], 1)
        self.assertEqual(calls["desktop"], 0, "裸命令不该启动桌面端")

    def test_help_flag_prints_help(self):
        for flag in ("--help", "-h"):
            _code, calls = self._main([flag])
            self.assertEqual(calls["help"], 1, msg=flag)

    def test_gui_flag_launches_the_desktop(self):
        with mock.patch.object(self.runmod, "_has_desktop_environment", lambda: True):
            code, calls = self._main(["--gui"])
        self.assertEqual(code, 0)
        self.assertEqual(calls["desktop"], 1)

    def test_desktop_alias_also_works(self):
        with mock.patch.object(self.runmod, "_has_desktop_environment", lambda: True):
            _code, calls = self._main(["--desktop"])
        self.assertEqual(calls["desktop"], 1)

    def test_gui_without_a_display_refuses_with_a_reason(self):
        # 与其让 pip 去编译一个装不上的 PyQt6，不如直接说清楚。
        with mock.patch.object(self.runmod, "_has_desktop_environment", lambda: False):
            code, calls = self._main(["--gui"])
        self.assertEqual(code, 1)
        self.assertEqual(calls["desktop"], 0)

    def test_shell_still_works(self):
        _code, calls = self._main(["shell"])
        self.assertEqual(calls["shell"], 1)

    def test_help_mode_needs_no_dependency_check(self):
        self.assertFalse(self.runmod._requires_full_dependencies("help", []))

    def test_desktop_mode_still_checks_gui_dependencies(self):
        # --gui 时要自动补装，所以这里必须仍然返回 True。
        self.assertTrue(self.runmod._requires_full_dependencies("desktop", []))
        self.assertIn("PyQt6", self.runmod._required_imports("desktop"))
        self.assertNotIn("PyQt6", self.runmod._required_imports("shell"))
