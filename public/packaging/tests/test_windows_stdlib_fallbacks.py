"""Windows 上缺失的 Unix 专有标准库模块，应降级而不是启动失败。

[EN] Unix-only stdlib modules that Windows does not ship must degrade
gracefully instead of taking the process down at import time.
"""

import importlib
import sys
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[3]
SRC = str(REPO_ROOT / "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)


class ReadlineOptionalTest(unittest.TestCase):
    """``readline`` 只有 Unix 有；Windows 上 shell 应当照常启动，只是没有历史。"""

    def test_interactive_cli_imports_without_readline(self):
        from workflows.interfaces import interactive_cli

        # Restore the real module once the patch is off again, so the reload
        # below picks readline back up for any later test.
        self.addCleanup(importlib.reload, interactive_cli)

        # Binding the name to None makes ``import readline`` raise ImportError,
        # which is what happens on a stock Windows interpreter.
        with mock.patch.dict(sys.modules, {"readline": None}):
            reloaded = importlib.reload(interactive_cli)
            self.assertIsNone(reloaded.readline)
            shell = object.__new__(reloaded.InteractiveCLI)
            # History load/save must be no-ops rather than AttributeError.
            shell.preloop()
            shell.postloop()

    def test_readline_is_used_when_present(self):
        from workflows.interfaces import interactive_cli

        if "readline" not in sys.modules:
            self.skipTest("本平台没有 readline")
        self.assertIsNotNone(interactive_cli.readline)


if __name__ == "__main__":
    unittest.main()
