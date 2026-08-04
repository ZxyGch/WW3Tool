"""WW3TOOL_ROOT 路径解析测试（pip/brew 打包形态的根目录语义）。

每个用例在独立子进程中运行：模块级 ``PROJECT_ROOT`` / ``LOGO_PATH`` 等
在 import 时即求值，同进程内设置/清除环境变量会互相污染。

[EN] Repo-root resolution tests for the WW3TOOL_ROOT env override.
Each case runs in its own subprocess: module-level constants are evaluated
at import time, so mutating the env in-process would leak between cases.
"""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = str(REPO_ROOT / "src")


def _run(env_root: Optional[str], code: str) -> str:
    env = os.environ.copy()
    if env_root is None:
        env.pop("WW3TOOL_ROOT", None)
    else:
        env["WW3TOOL_ROOT"] = env_root
    return subprocess.check_output(
        [sys.executable, "-c", code], env=env, text=True, cwd=REPO_ROOT
    ).strip()


class Ww3toolRootEnvTest(unittest.TestCase):
    """设置 WW3TOOL_ROOT 后，各处根解析应一致指向该目录。"""

    def test_runtime_config_project_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = _run(
                tmp,
                "import sys; sys.path.insert(0, %r);\n"
                "from workflows.infrastructure.runtime_config import PROJECT_ROOT;\n"
                "import os; print(os.path.normpath(PROJECT_ROOT))" % SRC,
            )
        self.assertEqual(out, os.path.normpath(tmp))

    def test_workdir_setup_repo_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = _run(
                tmp,
                "import sys; sys.path.insert(0, %r);\n"
                "from workflows.interfaces.workdir_setup import repo_root_path;\n"
                "print(repo_root_path())" % SRC,
            )
        self.assertEqual(Path(out), Path(tmp).resolve())

    def test_desktop_repo_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = _run(
                tmp,
                "import sys; sys.path.insert(0, %r);\n"
                "from desktop._repo_root import repo_root;\n"
                "print(repo_root())" % SRC,
            )
        self.assertEqual(Path(out), Path(tmp).resolve())

    def test_translations_loads_from_env_root(self):
        # 语言文件应从 WW3TOOL_ROOT/public/languages/ 读取；
        # 空临时目录下返回空字典而非崩溃。
        with tempfile.TemporaryDirectory() as tmp:
            out = _run(
                tmp,
                "import sys; sys.path.insert(0, %r);\n"
                "from workflows.support.translations import _load_language;\n"
                "print(sorted(_load_language('en').items()))" % SRC,
            )
        self.assertEqual(out, "[]")

    def test_translations_reads_real_file_from_env_root(self):
        # 正向用例：WW3TOOL_ROOT 下有 public/languages/en.json 时应真实读到。
        with tempfile.TemporaryDirectory() as tmp:
            langs = Path(tmp) / "public" / "languages"
            langs.mkdir(parents=True)
            (langs / "en.json").write_text('{"key_hello": "hello"}', encoding="utf-8")
            out = _run(
                tmp,
                "import sys; sys.path.insert(0, %r);\n"
                "from workflows.support.translations import _load_language;\n"
                "print(_load_language('en').get('key_hello'))" % SRC,
            )
        self.assertEqual(out, "hello")


class Ww3toolRootInferTest(unittest.TestCase):
    """未设置 WW3TOOL_ROOT 时，各处应回退到仓库布局推断（与以往一致）。"""

    def test_runtime_config_infers_repo_root(self):
        out = _run(
            None,
            "import sys; sys.path.insert(0, %r);\n"
            "from workflows.infrastructure.runtime_config import PROJECT_ROOT;\n"
            "import os; print(os.path.normpath(PROJECT_ROOT))" % SRC,
        )
        self.assertEqual(out, os.path.normpath(str(REPO_ROOT)))

    def test_desktop_infers_repo_root(self):
        out = _run(
            None,
            "import sys; sys.path.insert(0, %r);\n"
            "from desktop._repo_root import repo_root;\n"
            "print(repo_root())" % SRC,
        )
        self.assertEqual(Path(out), REPO_ROOT)

    def test_workdir_setup_infers_repo_root(self):
        out = _run(
            None,
            "import sys; sys.path.insert(0, %r);\n"
            "from workflows.interfaces.workdir_setup import repo_root_path;\n"
            "print(repo_root_path())" % SRC,
        )
        self.assertEqual(Path(out), REPO_ROOT)


if __name__ == "__main__":
    unittest.main()
