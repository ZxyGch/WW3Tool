"""MCP server 交给 AI 客户端的应当是结构化结果，不是一段日志文本。

MCP 是这个工具面向 AI 的主接口。它此前把 CLI 的 stdout 原样当文本返回，
客户端仍然只能靠关键词去猜成败——CLI 层已经有 --json 了，这里不该再退回
散文。

模块顶层 import 了 mcp 框架（需要 Python 3.10+），本机 venv 装不上，所以
只加载到那一行为止，单独验证 _run_cli。
"""

import json
import subprocess
import sys
import types
import unittest
from unittest import mock
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
MCP_PY = REPO_ROOT / "public" / "packaging" / "mcp" / "ww3tool_mcp.py"


def _load_run_cli():
    """执行模块源码到 mcp 框架导入之前，取出 _run_cli。"""
    src = MCP_PY.read_text(encoding="utf-8")
    marker = "from mcp.server.fastmcp import FastMCP"
    head = src.split(marker)[0]
    module = types.ModuleType("ww3tool_mcp_head")
    module.__file__ = str(MCP_PY)
    exec(compile(head, str(MCP_PY), "exec"), module.__dict__)
    return module


@unittest.skipUnless(MCP_PY.is_file(), "仓库里没有 MCP server")
class RunCliResultTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = _load_run_cli()

    def test_it_asks_the_cli_for_json(self):
        captured = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            return subprocess.CompletedProcess(
                cmd, 0, stdout='{"command":"config","status":"ok","exit_code":0}',
                stderr="")

        with mock.patch.object(self.mod.subprocess, "run", fake_run):
            self.mod._run_cli("config", ["/tmp/wd"])
        self.assertIn("--json", captured["cmd"])
        # --json 必须在子命令之前（它是全局参数）
        self.assertLess(captured["cmd"].index("--json"),
                        captured["cmd"].index("config"))

    def test_result_is_valid_json_for_the_client(self):
        def fake_run(cmd, **kwargs):
            return subprocess.CompletedProcess(
                cmd, 0,
                stdout='{"command":"config","status":"ok","exit_code":0,'
                       '"outputs":["/tmp/grid.bot"]}',
                stderr="")

        with mock.patch.object(self.mod.subprocess, "run", fake_run):
            payload = json.loads(self.mod._run_cli("config", []))
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["outputs"], ["/tmp/grid.bot"])

    def test_non_json_output_is_reported_honestly(self):
        # 极早期失败时 CLI 可能来不及产出对象，此时不能假装成功。
        def fake_run(cmd, **kwargs):
            return subprocess.CompletedProcess(cmd, 2, stdout="boom",
                                               stderr="bad config")

        with mock.patch.object(self.mod.subprocess, "run", fake_run):
            payload = json.loads(self.mod._run_cli("config", []))
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["exit_code"], 2)
        self.assertIn("bad config", payload["error"]["message"])

    def test_timeout_is_structured_too(self):
        def fake_run(cmd, **kwargs):
            raise subprocess.TimeoutExpired(cmd, 1)

        with mock.patch.object(self.mod.subprocess, "run", fake_run):
            payload = json.loads(self.mod._run_cli("local-run", [], timeout=1))
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["exit_code"], 124)
        self.assertEqual(payload["error"]["kind"], "timeout")
        self.assertTrue(payload["error"].get("hints"))

    def test_stderr_is_kept_alongside(self):
        def fake_run(cmd, **kwargs):
            return subprocess.CompletedProcess(
                cmd, 0, stdout='{"command":"c","status":"ok","exit_code":0}',
                stderr="a warning")

        with mock.patch.object(self.mod.subprocess, "run", fake_run):
            payload = json.loads(self.mod._run_cli("c", []))
        self.assertIn("a warning", payload["stderr"])


if __name__ == "__main__":
    unittest.main()
