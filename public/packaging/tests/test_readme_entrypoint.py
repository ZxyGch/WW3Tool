"""README 里的入口说明必须跟 run.py 的实际分派一致。

不带参数曾经启动 GUI，改成打印帮助之后两份 README 都留在了旧说法上，
到用户手里才被发现。这里把"文档说的"和"代码做的"钉在一起。

[EN] Keep the README entry-point docs in step with run.py's actual dispatch.
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
READMES = ("README.md", "README.zh-CN.md")

# 形如 `ww3tool  # ...` / `python3 run.py  # ...` 的示例行（后面没有子命令）
_BARE_ENTRY = re.compile(r"^\s*(?:ww3tool|python3 run\.py)\s*#(?P<comment>.*)$")
_GUI_WORDS = re.compile(r"GUI|图形界面|desktop|桌面端", re.IGNORECASE)


class ReadmeEntryPointTest(unittest.TestCase):
    def _lines(self, name):
        return (ROOT / name).read_text(encoding="utf-8").splitlines()

    def test_bare_invocation_is_not_documented_as_gui(self):
        for name in READMES:
            for lineno, line in enumerate(self._lines(name), 1):
                m = _BARE_ENTRY.match(line)
                if m and _GUI_WORDS.search(m.group("comment")):
                    self.fail(f"{name}:{lineno} 仍称不带参数会启动 GUI：{line.strip()}")

    def test_gui_flag_is_documented(self):
        for name in READMES:
            text = (ROOT / name).read_text(encoding="utf-8")
            self.assertIn("ww3tool --gui", text, name)
            self.assertIn("python3 run.py --gui", text, name)

    def test_run_py_still_dispatches_this_way(self):
        # 文档改对了但代码又改回去，同样要报错
        source = (ROOT / "run.py").read_text(encoding="utf-8")
        self.assertIn('if not rest:\n        mode = "help"', source)
        self.assertIn('elif rest[0] in _GUI_FLAGS:\n        mode = "desktop"', source)


if __name__ == "__main__":
    unittest.main()
