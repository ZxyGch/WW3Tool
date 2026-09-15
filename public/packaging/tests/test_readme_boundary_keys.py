"""params.yml 的 boundary 段每个键、以及边界相关子命令，都必须在两份 README 里写到。

外部边界谱首次发布时，CLI 命令只在中文 README 的命令表里出现，英文 README 与
配置说明一处都没有。与 test_readme_forcing_keys 同理，把文档与模板钉在一起。

[EN] Every key under params.yml's boundary section, and every boundary subcommand,
must appear in both READMEs, so the docs cannot fall behind the template again.
"""

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
READMES = ("README.md", "README.zh-CN.md")
BOUNDARY_COMMANDS = ("inspect-boundary", "prepare-boundary", "boundary-status", "download-boundary-report")


def _boundary_keys():
    """读 params.yml 的 boundary 段各层键（不引入 yaml 依赖，按缩进解析）。"""
    keys = []
    inside = False
    for line in (ROOT / "params.yml").read_text(encoding="utf-8").splitlines():
        if line.startswith("boundary:"):
            inside = True
            continue
        if inside:
            if line and not line.startswith(" ") and not line.startswith("#"):
                break
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or stripped.startswith("-") or ":" not in stripped:
                continue
            name = stripped.split(":", 1)[0].strip()
            if name and name not in keys:
                keys.append(name)
    return keys


class BoundaryDocumentedTest(unittest.TestCase):
    def test_the_parser_found_the_section(self):
        keys = _boundary_keys()
        for expected in ("mode", "source", "files", "sides", "max_distance_km", "max_time_gap_seconds"):
            self.assertIn(expected, keys)

    def test_every_boundary_key_is_documented(self):
        keys = _boundary_keys()
        for name in READMES:
            text = (ROOT / name).read_text(encoding="utf-8")
            missing = [k for k in keys if k not in text]
            self.assertEqual(missing, [], msg=f"{name} 未提到 boundary 的这些键：{missing}")

    def test_every_boundary_command_is_documented(self):
        for name in READMES:
            text = (ROOT / name).read_text(encoding="utf-8")
            missing = [c for c in BOUNDARY_COMMANDS if c not in text]
            self.assertEqual(missing, [], msg=f"{name} 未提到这些边界子命令：{missing}")


if __name__ == "__main__":
    unittest.main()
