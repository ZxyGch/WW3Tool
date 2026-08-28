"""本地路径规范化测试（重点覆盖 Windows 的写法差异）。

[EN] Local path normalisation, with the Windows spellings the desktop
actually receives: Qt returns forward slashes, Explorer's "Copy as path"
adds quotes, and comparisons are case-insensitive.
"""

import ntpath
import os
import posixpath
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[3]
SRC = str(REPO_ROOT / "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from workflows.support import paths as paths_mod  # noqa: E402
from workflows.support.paths import (  # noqa: E402
    local_path_key,
    normalize_local_path,
    same_local_path,
)


def _fake_os(module, *, name, sep, cwd):
    """A stand-in for ``os`` that reports another platform's path rules."""
    fake = types.SimpleNamespace(path=module, name=name, sep=sep)
    fake.path = types.SimpleNamespace(
        expandvars=module.expandvars,
        expanduser=module.expanduser,
        normpath=module.normpath,
        normcase=module.normcase,
        # abspath goes through the real cwd otherwise, which is the host's.
        abspath=lambda p: p if module.isabs(p) else module.join(cwd, p),
    )
    return fake


def as_windows():
    return mock.patch.object(
        paths_mod, "os", _fake_os(ntpath, name="nt", sep="\\", cwd="C:\\work"))


def as_posix():
    return mock.patch.object(
        paths_mod, "os", _fake_os(posixpath, name="posix", sep="/", cwd="/work"))


class NormalizeOnWindowsTest(unittest.TestCase):
    def test_qt_forward_slashes_become_backslashes(self):
        # QFileDialog returns forward slashes on Windows too; everything the
        # app builds with os.path.join uses backslashes.
        with as_windows():
            self.assertEqual(normalize_local_path("C:/Users/zxy/workSpace"),
                             r"C:\Users\zxy\workSpace")

    def test_copy_as_path_quotes_are_stripped(self):
        with as_windows():
            self.assertEqual(normalize_local_path('"C:\\Users\\zxy\\a.nc"'),
                             r"C:\Users\zxy\a.nc")
            self.assertEqual(normalize_local_path("'C:/Users/zxy'"), r"C:\Users\zxy")

    def test_bare_drive_gets_a_separator(self):
        with as_windows():
            self.assertEqual(normalize_local_path("C:"), "C:\\")

    def test_unc_path_survives(self):
        with as_windows():
            self.assertEqual(normalize_local_path("//server/share/data"),
                             r"\\server\share\data")

    def test_relative_path_stays_relative(self):
        with as_windows():
            self.assertEqual(normalize_local_path("public/forcing"), r"public\forcing")

    def test_redundant_segments_collapse(self):
        with as_windows():
            self.assertEqual(normalize_local_path(r"C:\a\.\b\..\c"), r"C:\a\c")


class NormalizeOnPosixTest(unittest.TestCase):
    def test_plain_path_is_untouched(self):
        with as_posix():
            self.assertEqual(normalize_local_path("/Users/zxy/workSpace"),
                             "/Users/zxy/workSpace")

    def test_quotes_are_stripped(self):
        with as_posix():
            self.assertEqual(normalize_local_path('"/Users/zxy/a.nc"'), "/Users/zxy/a.nc")

    def test_relative_path_stays_relative(self):
        with as_posix():
            self.assertEqual(normalize_local_path("public/forcing"), "public/forcing")


class EmptyValueTest(unittest.TestCase):
    def test_blank_inputs_stay_blank(self):
        for value in (None, "", "   ", '""', "''"):
            self.assertEqual(normalize_local_path(value), "", msg=repr(value))
            self.assertEqual(local_path_key(value), "", msg=repr(value))


class SameLocalPathTest(unittest.TestCase):
    def test_windows_separator_and_case_do_not_matter(self):
        with as_windows():
            self.assertTrue(same_local_path("C:/Users/zxy/ws", r"C:\Users\ZXY\ws"))
            self.assertTrue(same_local_path(r'"C:\Users\zxy\ws"', "C:/Users/zxy/ws/"))
            self.assertFalse(same_local_path("C:/Users/zxy/ws", r"C:\Users\zxy\other"))

    def test_posix_is_case_sensitive(self):
        with as_posix():
            self.assertTrue(same_local_path("/a/b/../b", "/a/b"))
            self.assertFalse(same_local_path("/a/b", "/a/B"))

    def test_relative_resolves_against_cwd(self):
        with as_windows():
            self.assertTrue(same_local_path("sub/dir", r"C:\work\sub\dir"))


class RuntimeConfigHelpersTest(unittest.TestCase):
    """runtime_config 里依赖路径写法的判定。"""

    def setUp(self):
        from workflows.infrastructure import runtime_config

        self.rc = runtime_config

    def test_quoted_foreign_path_is_still_detected(self):
        # Explorer's "Copy as path" wraps the value in quotes; the
        # cross-platform residue check has to see through them.
        foreign = "C:\\Users\\zxy" if os.name != "nt" else "/Users/zxy"
        self.assertFalse(self.rc._is_local_path_compatible(foreign))
        self.assertFalse(self.rc._is_local_path_compatible(f'"{foreign}"'))
        self.assertFalse(self.rc._is_local_path_compatible(f"'{foreign}'"))

    def test_native_path_stays_compatible(self):
        native = os.path.abspath(os.sep + "tmp")
        self.assertTrue(self.rc._is_local_path_compatible(native))
        self.assertTrue(self.rc._is_local_path_compatible(f'"{native}"'))

    def test_recent_workdir_key_folds_spellings(self):
        base = os.path.abspath(os.path.join(os.sep, "tmp", "ws"))
        detour = os.path.join(os.path.dirname(base), "other", "..", os.path.basename(base))
        self.assertEqual(self.rc._recent_workdir_key(base),
                         self.rc._recent_workdir_key(detour))
        self.assertEqual(self.rc._recent_workdir_key(base),
                         self.rc._recent_workdir_key(f'"{base}"'))


class RootParamsGuardTest(unittest.TestCase):
    """CLI 判断"这是仓库根模板 params.yml"时不能被大小写/写法差异骗过。"""

    def test_spelling_variants_still_match(self):
        from workflows.interfaces.command_line import _is_root_params

        root_params = REPO_ROOT / "params.yml"
        if not root_params.exists():
            self.skipTest("仓库根 params.yml 不存在")
        self.assertTrue(_is_root_params(root_params))
        detour = root_params.parent / "src" / ".." / "params.yml"
        self.assertTrue(_is_root_params(detour))
        self.assertFalse(_is_root_params(REPO_ROOT / "pyproject.toml"))


class RealPlatformTest(unittest.TestCase):
    """未打桩时必须与当前平台的 os.path 行为一致。"""

    def test_matches_os_path_normpath(self):
        sample = os.path.join("some", "dir", "file.nc")
        self.assertEqual(normalize_local_path(sample), os.path.normpath(sample))

    def test_home_expands(self):
        self.assertEqual(normalize_local_path("~"), os.path.normpath(str(Path.home())))


if __name__ == "__main__":
    unittest.main()
