"""用户配置不能存在 site-packages 里。

pip 升级的做法是「删掉旧版全部文件 → 装新版」，所以存在包目录里的设置
（服务器地址、各 WW3 版本可执行路径、7 GB 参考数据的位置）会在每次
pip install --upgrade 后全部丢失。集群上实测确认过。
"""

import os
import subprocess
import sys
import textwrap
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SRC = REPO_ROOT / "src"


def _probe(code, env_extra, tmp):
    """在独立进程里跑一段探针——模块级常量只在 import 时求值一次。"""
    env = dict(os.environ)
    env.pop("WW3TOOL_PARAMS", None)
    env.pop("WW3TOOL_ROOT", None)
    env["PYTHONPATH"] = str(SRC)
    env["HOME"] = str(tmp / "home")
    env["XDG_CONFIG_HOME"] = str(tmp / "home" / ".config")
    env["APPDATA"] = str(tmp / "home" / "AppData" / "Roaming")
    env.update(env_extra)
    out = subprocess.run([sys.executable, "-c", textwrap.dedent(code)],
                         capture_output=True, text=True, env=env)
    if out.returncode != 0:
        raise AssertionError(out.stderr[-2000:])
    return out.stdout.strip()


class PackagedLayoutTest(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._tmpdir = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmpdir.name)
        (self.tmp / "home").mkdir(parents=True, exist_ok=True)
        self.pkg = self.tmp / "ww3tool_resources"
        self.pkg.mkdir(parents=True, exist_ok=True)
        (self.pkg / "params.yml").write_text(
            "server:\n  host:\ngrid:\n  reference_data_path:\n", encoding="utf-8")

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_packaged_install_keeps_config_outside_site_packages(self):
        got = _probe("""
            from workflows.infrastructure import runtime_config as rc
            print(rc.PARAMS_FILE)
        """, {"WW3TOOL_ROOT": str(self.pkg)}, self.tmp)
        self.assertNotIn("ww3tool_resources", got,
                         "配置不该落在包目录里——升级会被删掉")
        self.assertTrue(got.startswith(str(self.tmp / "home")), got)

    def test_existing_settings_are_carried_over_on_first_run(self):
        # 老用户的设置此前就在包内那份里，首次运行要搬过去而不是丢掉。
        (self.pkg / "params.yml").write_text(
            "server:\n  host: MY-CLUSTER\n", encoding="utf-8")
        got = _probe("""
            from workflows.infrastructure import runtime_config as rc
            print(open(rc.PARAMS_FILE, encoding='utf-8').read())
        """, {"WW3TOOL_ROOT": str(self.pkg)}, self.tmp)
        self.assertIn("MY-CLUSTER", got)

    def test_upgrade_does_not_touch_the_user_copy(self):
        code = """
            from workflows.infrastructure import runtime_config as rc
            import pathlib
            p = pathlib.Path(rc.PARAMS_FILE)
            p.write_text('server:\\n  host: KEEP-ME\\n', encoding='utf-8')
            # 模拟升级：包内模板被替换
            pathlib.Path(rc.BUNDLED_PARAMS_FILE).write_text(
                'server:\\n  host:\\n', encoding='utf-8')
            import importlib
            importlib.reload(rc)
            print('KEEP-ME' in pathlib.Path(rc.PARAMS_FILE).read_text(encoding='utf-8'))
        """
        self.assertEqual(_probe(code, {"WW3TOOL_ROOT": str(self.pkg)}, self.tmp), "True")

    def test_env_override_wins(self):
        target = self.tmp / "custom" / "my.yml"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("server:\n", encoding="utf-8")
        got = _probe("""
            from workflows.infrastructure import runtime_config as rc
            print(rc.PARAMS_FILE)
        """, {"WW3TOOL_ROOT": str(self.pkg), "WW3TOOL_PARAMS": str(target)}, self.tmp)
        self.assertEqual(got, str(target))


class RepoLayoutTest(unittest.TestCase):
    """仓库形态行为不变：还是用仓库里那份。"""

    @unittest.skipUnless((REPO_ROOT / "run.py").is_file(), "需要仓库形态")
    def test_repo_uses_its_own_params(self):
        sys.path.insert(0, str(SRC))
        from workflows.infrastructure import runtime_config as rc
        self.assertFalse(rc._is_packaged_layout())
        self.assertEqual(rc.PARAMS_FILE, rc.BUNDLED_PARAMS_FILE)


class ConfigDirConventionTest(unittest.TestCase):
    """各平台的配置目录惯例。"""

    def setUp(self):
        sys.path.insert(0, str(SRC))
        from workflows.infrastructure import runtime_config as rc
        self.rc = rc

    def test_current_platform_dir_is_under_home(self):
        got = self.rc._user_config_dir()
        self.assertIn("ww3tool", got)
        self.assertTrue(os.path.isabs(got))


if __name__ == "__main__":
    unittest.main()
