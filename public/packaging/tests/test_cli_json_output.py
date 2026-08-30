"""CLI 的机器可读接口。

给 AI 或脚本调用时，散文输出只能靠关键词匹配判断成败，很脆弱。--json 下
stdout 上必须**只有一个**可解析的 JSON 对象，且失败原因要在里面，而不是
只去 stderr。
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
RUN_PY = REPO_ROOT / "run.py"
PYTHON = sys.executable


def _run(*argv):
    out = subprocess.run([PYTHON, str(RUN_PY), *argv],
                         capture_output=True, text=True, cwd=str(REPO_ROOT))
    return out


@unittest.skipUnless(RUN_PY.is_file(), "需要仓库形态")
class JsonEnvelopeTest(unittest.TestCase):
    def test_stdout_is_exactly_one_json_object(self):
        out = _run("--json", "print-example")
        # 关键：启动阶段的依赖提示等都不能混进 stdout
        payload = json.loads(out.stdout)
        self.assertEqual(payload["command"], "print-example")

    def test_envelope_has_the_fields_a_caller_needs(self):
        payload = json.loads(_run("--json", "print-example").stdout)
        for key in ("command", "status", "exit_code", "seconds"):
            self.assertIn(key, payload)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["exit_code"], 0)

    def test_human_output_is_kept_as_messages(self):
        payload = json.loads(_run("--json", "print-example").stdout)
        self.assertTrue(payload.get("messages"))

    def test_without_the_flag_output_stays_prose(self):
        out = _run("print-example")
        with self.assertRaises(json.JSONDecodeError):
            json.loads(out.stdout)


@unittest.skipUnless(RUN_PY.is_file(), "需要仓库形态")
class SchemaCommandTest(unittest.TestCase):
    """配置结构要能自省，否则只能去读源码。"""

    def setUp(self):
        self.schema = json.loads(_run("--json", "schema").stdout)["data"]

    def test_lists_fields_with_paths_and_types(self):
        self.assertGreater(len(self.schema["fields"]), 10)
        for field in self.schema["fields"]:
            self.assertIn("path", field)
            self.assertIn("type", field)

    def test_documents_where_the_two_params_files_live(self):
        self.assertIn("global", self.schema["files"])
        self.assertIn("workdir", self.schema["files"])

    def test_explains_the_non_obvious_dx_location(self):
        # normal 网格的 dx 藏在 nested.levels[0] 里，这条必须写明。
        dx = [f for f in self.schema["fields"] if f["path"].endswith(".dx")]
        self.assertTrue(dx)
        self.assertIn("normal", dx[0].get("note", ""))

    def test_enums_carry_their_valid_values(self):
        coast = [f for f in self.schema["fields"]
                 if f["path"].endswith("coastline_precision")][0]
        self.assertIn("full", coast["options"])
        self.assertIn("low", coast["options"])

    def test_environment_variables_are_listed(self):
        names = {e["name"] for e in self.schema["environment"]}
        self.assertIn("WW3TOOL_PARAMS", names)
        self.assertIn("WW3TOOL_MESHGEN_WORKERS", names)


@unittest.skipUnless(RUN_PY.is_file(), "需要仓库形态")
class FailureReportingTest(unittest.TestCase):
    """失败原因必须出现在 JSON 里。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.wd = Path(self._tmp.name) / "wd"
        _run("workdir", str(self.wd))

    def tearDown(self):
        self._tmp.cleanup()

    def test_config_error_is_reported_with_reason_and_hints(self):
        out = _run("--json", "validate", "--stage", "full", str(self.wd))
        payload = json.loads(out.stdout)
        self.assertEqual(payload["status"], "error")
        self.assertIn("error", payload)
        self.assertTrue(payload["error"]["message"], "失败原因不能为空")
        self.assertTrue(payload["error"].get("hints"), "应给出可操作的下一步")

    def test_exit_code_matches_the_envelope(self):
        out = _run("--json", "validate", "--stage", "full", str(self.wd))
        payload = json.loads(out.stdout)
        self.assertEqual(payload["exit_code"], out.returncode)


@unittest.skipUnless(RUN_PY.is_file(), "需要仓库形态")
class StagedValidationTest(unittest.TestCase):
    """只想确认网格配置时，不该被还没准备的风场卡住。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.wd = Path(self._tmp.name) / "wd"
        _run("workdir", str(self.wd))
        import yaml
        p = self.wd / "params.yml"
        d = yaml.safe_load(p.read_text(encoding="utf-8"))
        g = d["grid"]
        g["lon"] = [120.0, 124.0]
        g["lat"] = [28.0, 32.0]
        g["reference_data_path"] = str(REPO_ROOT / "meshgen" / "reference_data")
        lv = g["structured"]["nested"]["levels"]
        lv[0].update(dx=0.1, dy=0.1, lon=[120.0, 124.0], lat=[28.0, 32.0])
        p.write_text(yaml.safe_dump(d, allow_unicode=True, sort_keys=False),
                     encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def test_grid_stage_passes_without_forcing(self):
        payload = json.loads(_run("--json", "validate", "--stage", "grid",
                                  str(self.wd)).stdout)
        self.assertEqual(payload["status"], "ok", payload.get("error"))

    def test_full_stage_still_requires_forcing(self):
        payload = json.loads(_run("--json", "validate", "--stage", "full",
                                  str(self.wd)).stdout)
        self.assertEqual(payload["status"], "error")


if __name__ == "__main__":
    unittest.main()
