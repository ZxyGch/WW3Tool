"""语言选择：显式配置优先，否则跟随环境，认不出一律退回英文。

发行模板里 desktop.language 必须是 auto —— 早期版本把打包那台机器的
界面语言写死进模板，用户新装后不论环境都拿到中文。

[EN] Language selection: an explicit setting wins, otherwise follow the
environment, and fall back to English when unrecognized.
"""

import importlib.util
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
_LOCALE_VARS = ("LC_ALL", "LC_MESSAGES", "LANG", "LANGUAGE")


def _load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class LanguageNormalizationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(ROOT / "src"))
        from workflows.support import translations

        cls.tx = translations

    def test_locale_spellings_map_to_bundled_codes(self):
        for value in ("zh_CN", "zh-Hans", "zh_CN.UTF-8", "zh", "ZH_cn"):
            self.assertEqual(self.tx.normalize_language(value), "zh_CN", value)
        for value in ("en_US", "en-GB", "en_US.UTF-8", "en"):
            self.assertEqual(self.tx.normalize_language(value), "en_US", value)

    def test_auto_and_neutral_locales_defer_to_caller(self):
        for value in ("", "   ", "auto", "system", "C", "POSIX", "c", None):
            self.assertIsNone(self.tx.normalize_language(value), value)

    def test_unshipped_language_is_not_recognized(self):
        # 没有语言包的语种交回调用方，由它退回英文，而不是退回中文
        for value in ("ja_JP", "de_DE", "fr", "ru_RU.UTF-8"):
            self.assertIsNone(self.tx.normalize_language(value), value)


class EnvironmentLanguageTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(ROOT / "src"))
        from workflows.support import translations

        cls.tx = translations

    def _with_env(self, **overrides):
        env = {k: v for k, v in os.environ.items() if k not in _LOCALE_VARS}
        env.update(overrides)
        return mock.patch.dict(os.environ, env, clear=True)

    def test_lang_selects_chinese(self):
        with self._with_env(LANG="zh_CN.UTF-8"):
            self.assertEqual(self.tx.language_from_environment(), "zh_CN")

    def test_lc_all_wins_over_lang(self):
        # LC_ALL=C 是"不要本地化"，不应再去看 LANG（集群 ssh 常这么设）
        with self._with_env(LC_ALL="C", LANG="zh_CN.UTF-8"):
            self.assertEqual(self.tx.language_from_environment(), "en_US")

    def test_lc_messages_outranks_lang(self):
        with self._with_env(LC_MESSAGES="zh_CN.UTF-8", LANG="en_US.UTF-8"):
            self.assertEqual(self.tx.language_from_environment(), "zh_CN")

    def test_language_list_takes_first_entry(self):
        with self._with_env(LANGUAGE="zh_CN:en_US"):
            self.assertEqual(self.tx.language_from_environment(), "zh_CN")

    def test_unset_environment_falls_back_to_english(self):
        with self._with_env():
            with mock.patch.object(self.tx, "_windows_ui_language", return_value=None):
                self.assertEqual(self.tx.language_from_environment(), "en_US")

    def test_unshipped_locale_falls_back_to_english(self):
        with self._with_env(LANG="ja_JP.UTF-8"):
            self.assertEqual(self.tx.language_from_environment(), "en_US")


class ResolveLanguageTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(ROOT / "src"))
        from workflows.support import translations

        cls.tx = translations

    def _with_config(self, value):
        from workflows.infrastructure import runtime_config

        return mock.patch.object(runtime_config, "load_config",
                                 return_value={"LANGUAGE": value})

    def _env(self, **overrides):
        env = {k: v for k, v in os.environ.items() if k not in _LOCALE_VARS}
        env.update(overrides)
        return mock.patch.dict(os.environ, env, clear=True)

    def test_explicit_setting_beats_environment(self):
        with self._with_config("en_US"), self._env(LANG="zh_CN.UTF-8"):
            self.assertEqual(self.tx.resolve_language(), "en_US")

    def test_auto_defers_to_environment(self):
        with self._with_config("auto"), self._env(LANG="zh_CN.UTF-8"):
            self.assertEqual(self.tx.resolve_language(), "zh_CN")

    def test_blank_setting_defers_to_environment(self):
        with self._with_config(None), self._env(LANG="zh_CN.UTF-8"):
            self.assertEqual(self.tx.resolve_language(), "zh_CN")

    def test_unreadable_config_defers_to_environment(self):
        # 首次运行、家目录只读、YAML 损坏——都不该硬退回某一种语言
        from workflows.infrastructure import runtime_config

        with mock.patch.object(runtime_config, "load_config",
                               side_effect=RuntimeError("broken")):
            with self._env(LANG="zh_CN.UTF-8"):
                self.assertEqual(self.tx.resolve_language(), "zh_CN")
            with self._env(LANG="en_US.UTF-8"):
                self.assertEqual(self.tx.resolve_language(), "en_US")

    def test_set_language_auto_returns_to_environment(self):
        original = self.tx._current_language
        try:
            with self._env(LANG="zh_CN.UTF-8"):
                self.tx.set_language("en_US")
                self.assertEqual(self.tx._current_language, "en_US")
                self.tx.set_language("auto")
                self.assertEqual(self.tx._current_language, "zh_CN")
        finally:
            self.tx._current_language = original
            self.tx._translations = {}


class ShippedTemplateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runmod = _load("_run_for_lang", "run.py")

    def test_sanitizer_resets_developer_preferences(self):
        # 打包那一刻开发者的界面设置不该变成所有用户的默认值
        for lang, theme in (("zh_CN", "LIGHT"), ("en_US", "DARK")):
            text = f"desktop:\n  language: {lang}\n  theme: {theme}\n  run_mode: both\n"
            out = self.runmod._sanitize_params_template(text)
            self.assertIn("  language: auto\n", out, lang)
            self.assertIn("  theme: AUTO\n", out, theme)
            self.assertIn("  run_mode: both\n", out)

    def test_repo_template_ships_auto(self):
        # 仓库里这份既是开发者配置又是分发模板，直接写 auto，避免再次泄漏
        text = (ROOT / "params.yml").read_text(encoding="utf-8")
        self.assertIn("\n  language: auto\n", text)

    def test_release_gate_catches_leaked_language(self):
        gate = _load("_gate_for_lang", "public/packaging/verify_no_personal_data.py")
        member = "ww3tool-0.0.0.whl:ww3tool_resources/params.yml"
        clean = b"desktop:\n  language: auto\n  theme: AUTO\n"
        self.assertEqual(gate._scan_member(member, clean), [])
        leaked = b"desktop:\n  language: zh_CN\n  theme: AUTO\n"
        found = gate._scan_member(member, leaked)
        self.assertEqual(len(found), 1)
        self.assertIn("language", found[0])

    def test_sanitizer_keeps_language_files_parseable(self):
        # 清洗器是按 YAML 写的，曾经把语言包里的 "language" 键改成 YAML 形状，
        # 整份文件解析失败 —— 而 tr() 解析失败时静默退回源码里的中文默认值
        import json

        for name in ("public/languages/en_US.json", "public/languages/zh_CN.json"):
            raw = (ROOT / name).read_text(encoding="utf-8")
            before = json.loads(raw)
            after = json.loads(self.runmod._sanitize_config_text(raw))
            self.assertEqual(after, before, f"{name} 被清洗器改动了")

    def test_sanitizer_still_blanks_personal_paths_in_json(self):
        import json

        text = '{\n  "a": "/Users/somebody/secret",\n  "b": "keep"\n}'
        out = json.loads(self.runmod._sanitize_config_text(text))
        self.assertEqual(out, {"a": "", "b": "keep"})

    def test_release_gate_catches_broken_json(self):
        gate = _load("_gate_for_json", "public/packaging/verify_no_personal_data.py")
        member = "ww3tool-0.0.0.whl:ww3tool_resources/public/languages/en_US.json"
        self.assertEqual(gate._scan_member(member, b'{"language": "Language"}'), [])
        found = gate._scan_member(member, b'{"language": auto\n}')
        self.assertEqual(len(found), 1)
        self.assertIn("JSON", found[0])

    def test_gate_ignores_language_outside_params_yml(self):
        gate = _load("_gate_for_lang2", "public/packaging/verify_no_personal_data.py")
        # 语言包里的 "language" 是一条翻译，不是偏好设置，不该被判为泄漏
        data = b'{\n  "language": "\xe8\xaf\xad\xe8\xa8\x80\xe8\xae\xbe\xe7\xbd\xae"\n}'
        self.assertEqual(gate._scan_member("w.whl:public/languages/zh_CN.json", data), [])


if __name__ == "__main__":
    unittest.main()
