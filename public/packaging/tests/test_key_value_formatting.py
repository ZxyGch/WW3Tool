"""启动提示的排版：一行一项、键对齐。

被置空的路径原本用 ", " 拼成一行输出，而这些值是绝对路径，连起来几百字符，
终端里裹成一团没法看。
"""

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SRC = str(REPO_ROOT / "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from workflows.support.formatting import format_key_value_lines  # noqa: E402


class KeyValueLinesTest(unittest.TestCase):
    def test_one_entry_per_line(self):
        out = format_key_value_lines(["a=/x", "b=/y", "c=/z"])
        self.assertEqual(len(out.splitlines()), 3)

    def test_keys_are_aligned(self):
        out = format_key_value_lines(["short=/x", "much_longer_key=/y"])
        arrows = [line.index("→") for line in out.splitlines()]
        self.assertEqual(len(set(arrows)), 1, "箭头应当对齐")

    def test_null_entries_show_only_the_key(self):
        out = format_key_value_lines(["forcing.wind=null"])
        self.assertIn("forcing.wind", out)
        self.assertNotIn("null", out)
        self.assertNotIn("→", out)

    def test_entry_without_a_value_is_tolerated(self):
        self.assertIn("bare", format_key_value_lines(["bare"]))

    def test_empty_input_gives_empty_output(self):
        self.assertEqual(format_key_value_lines([]), "")

    def test_long_paths_are_not_joined_onto_one_line(self):
        long_path = "/Library/Frameworks/Python.framework/Versions/3.13/lib/python3.13/site-packages/x"
        out = format_key_value_lines([f"k{i}={long_path}" for i in range(5)])
        self.assertEqual(len(out.splitlines()), 5)
        for line in out.splitlines():
            self.assertTrue(line.startswith("    "), "每行应有缩进")

    def test_indent_and_arrow_are_configurable(self):
        out = format_key_value_lines(["a=/x"], indent="  ", arrow="=>")
        self.assertTrue(out.startswith("  a =>"))


class MessageHasNoStalePlaceholderTest(unittest.TestCase):
    """翻译条目改成了纯标题，不能再留 {keys} 占位符。"""

    def test_translations_dropped_the_placeholder(self):
        import json
        for name in ("zh_CN", "en_US"):
            path = REPO_ROOT / "public" / "languages" / f"{name}.json"
            if not path.is_file():
                self.skipTest(f"{name}.json 不存在")
            text = json.loads(path.read_text(encoding="utf-8"))["cli_paths_nulled"]
            self.assertNotIn("{keys}", text, msg=name)


if __name__ == "__main__":
    unittest.main()
