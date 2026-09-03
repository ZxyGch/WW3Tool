"""params.yml 的 forcing 段每个键都必须在两份 README 里写到。

custom（变量名自定义映射）和 remote_paths（服务器上的强迫场路径）长期只存在
于代码和 params.yml 注释里，README 的 Step 2 只字未提，用户遇到非标准变量名
的文件时无从下手。

[EN] Every key under params.yml's forcing section must appear in both READMEs.
"""

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
READMES = ("README.md", "README.zh-CN.md")


def _forcing_keys():
    """读 params.yml 的 forcing 段一级键（不引入 yaml 依赖，按缩进解析）。"""
    keys = []
    inside = False
    for line in (ROOT / "params.yml").read_text(encoding="utf-8").splitlines():
        if line.startswith("forcing:"):
            inside = True
            continue
        if inside:
            if line and not line.startswith(" ") and not line.startswith("#"):
                break
            if line.startswith("  ") and not line.startswith("   ") and ":" in line:
                name = line.strip().split(":", 1)[0].strip()
                if name and not name.startswith("#"):
                    keys.append(name)
    return keys


class ForcingKeysDocumentedTest(unittest.TestCase):
    def test_the_parser_found_the_section(self):
        keys = _forcing_keys()
        self.assertIn("wind", keys)
        self.assertIn("custom", keys)
        self.assertIn("remote_paths", keys)

    def test_every_forcing_key_is_documented(self):
        keys = _forcing_keys()
        for name in READMES:
            text = (ROOT / name).read_text(encoding="utf-8")
            missing = [k for k in keys if k not in text]
            self.assertEqual(missing, [], msg=f"{name} 未提到 forcing 的这些键：{missing}")

    def test_the_roles_of_each_field_are_documented(self):
        # 角色名写错就无从填起：level 是 value、ice 是 concentration，
        # 都不是望文生义的 u/v
        for name in READMES:
            text = (ROOT / name).read_text(encoding="utf-8")
            for role in ("longitude", "latitude", "time", "concentration", "thickness"):
                # 不用 assertIn：失败时它会把整份 README 打进报错信息
                self.assertTrue(role in text, msg=f"{name} 未提到角色 {role}")

    def test_the_two_features_are_named_explicitly(self):
        # 光扫裸键名不够：英文版本来就有 "custom output directory" 这类无关命中
        for name in READMES:
            text = (ROOT / name).read_text(encoding="utf-8")
            for token in ("forcing.custom", "forcing:\n  remote_paths"):
                self.assertTrue(
                    token in text or token.replace("\n  ", "\n    ") in text,
                    msg=f"{name} 没有明确写到 {token!r}")


if __name__ == "__main__":
    unittest.main()
