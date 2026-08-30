#!/usr/bin/env python3
"""WW3Tool MCP server（stdio）。

把 WW3Tool 的全部 CLI 子命令暴露为 MCP tools，供任意 MCP 客户端
（Claude Desktop / Cursor / 通用 stdio 客户端）调用。

设计要点：
- **零双份维护**：所有工具及其参数 schema 运行时从
  ``workflows.interfaces.command_line.build_parser()`` 自动提取，
  与 ``python3 run.py`` 的命令行保持一致。
- **执行方式**：每个 tool 通过子进程调用仓库根 ``run.py <command> ...``，
  复用其 venv 引导 / 依赖检查逻辑，输出与 CLI 完全一致。
- **安全**：破坏性远程操作（upload / clear-remote / cancel-job 等）
  保留了 CLI 自身的 ``--confirm`` 保护，LLM 必须显式传 ``True`` 才会执行。

启动（通常由 MCP 客户端拉起，无需手动执行）：
    mcp/.venv/bin/python mcp/ww3tool_mcp.py

[EN] WW3Tool MCP server (stdio). Exposes every CLI subcommand as an MCP tool.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
SRC_DIR = REPO_ROOT / "src"
RUN_PY = REPO_ROOT / "run.py"

# 让 server 可以 import workflows（仅用于读取命令定义，不执行任何任务）
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from workflows.interfaces.command_line import build_parser  # noqa: E402

TOOL_PREFIX = "ww3tool"


# ──────────────────────────────────────────────────────────────────────────
# CLI 执行
# ──────────────────────────────────────────────────────────────────────────


def _run_cli(command: str, argv: list[str], timeout: float = 3600.0) -> str:
    """以子进程执行 ``run.py --json <command> [argv...]`` 并返回结构化结果。

    走 ``--json``：客户端拿到的是一个对象——状态、退出码、产出文件清单、
    失败原因与可操作建议，而不是一段需要靠关键词去猜的日志文本。原本给人
    看的那些行仍保留在 ``messages`` 里。

    *timeout* 秒后仍未结束的任务会被终止（默认 1 小时，避免 MCP 请求无限挂起）。

    [EN] Return the CLI's structured result rather than a blob of prose.
    """
    try:
        proc = subprocess.run(
            [sys.executable, str(RUN_PY), "--json", command, *argv],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return json.dumps({
            "command": command,
            "status": "error",
            "exit_code": 124,
            "error": {
                "kind": "timeout",
                "message": f"command `{command}` timed out after {timeout:.0f}s",
                "hints": ["long tasks such as local-run or submit are better "
                          "started from the CLI and polled with check-status"],
            },
        }, ensure_ascii=False, indent=2)

    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").rstrip()
    try:
        payload = json.loads(out)
    except (ValueError, TypeError):
        # --json 没能产出对象（极早期的失败等）：如实回报，不假装成功。
        payload = {
            "command": command,
            "status": "ok" if proc.returncode == 0 else "error",
            "exit_code": proc.returncode,
            "messages": out.splitlines(),
        }
        if proc.returncode != 0:
            payload["error"] = {"kind": "cli", "message": err or out or "no output"}
    if err and "stderr" not in payload:
        payload["stderr"] = err.splitlines()
    return json.dumps(payload, ensure_ascii=False, indent=2)


# ──────────────────────────────────────────────────────────────────────────
# argparse → MCP 参数 schema
# ──────────────────────────────────────────────────────────────────────────

_SKIPPED_TYPES = (argparse._HelpAction, argparse._SubParsersAction)


def _py_type(action: argparse.Action) -> str:
    """把 argparse action 映射为 Python 类型注解字符串。"""
    base: str = "str"
    if action.type is not None and action.type is not str:
        base = {int: "int", float: "float"}.get(action.type, "str")

    if action.nargs in ("+", "*"):
        return f"list[{base}]"
    if action.nargs is not None and isinstance(action.nargs, int):
        # nargs=2 / nargs=4（如 --time-range START END、--bbox 4 个值）
        return f"list[{base}]"
    return base


def _describe_action(action: argparse.Action) -> str:
    parts = []
    if action.option_strings:
        parts.append(" / ".join(action.option_strings))
    else:
        parts.append(f"<{action.dest}>")
    if action.required:
        parts.append("required")
    if action.choices:
        parts.append("choices=" + ",".join(str(c) for c in action.choices))
    if action.default not in (None, argparse.SUPPRESS) and action.default is not False:
        parts.append(f"default={action.default}")
    if action.help and action.help is not argparse.SUPPRESS:
        parts.append(f": {action.help}")
    return " ".join(parts)


def _action_to_spec(action: argparse.Action) -> dict[str, Any]:
    """把一个 argparse action 转为参数规格。"""
    if action.option_strings:
        # 优先使用长选项名作为参数名：--download-ref-data → download_ref_data
        long_flags = [f for f in action.option_strings if f.startswith("--")]
        flag = (long_flags or action.option_strings)[0]
        pname = flag.lstrip("-").replace("-", "_")
        is_positional = False
    else:
        flag = None
        pname = action.dest
        is_positional = True

    is_bool = action.nargs is None and action.type is None and action.choices is None and not is_positional
    # store_true/store_false 之外，还有可能显式设了 const
    is_flag = is_bool and (action.const is not None or action.nargs is None and action.default in (True, False))

    default = action.default
    if default is argparse.SUPPRESS:
        default = None

    return {
        "pname": pname,
        "flag": flag,
        "positional": is_positional,
        "is_flag": is_flag,
        "ptype": "bool" if is_flag else _py_type(action),
        "default": default,
        "required": bool(action.required),
        "help": _describe_action(action),
    }


def _make_tool(command: str, subparser: argparse.ArgumentParser, tool_name: str):
    """为单个子命令生成一个 MCP tool 函数。"""
    specs = [
        _action_to_spec(a)
        for a in subparser._actions
        if not isinstance(a, _SKIPPED_TYPES)
    ]

    params: list[str] = []
    for s in sorted(specs, key=lambda x: 0 if x["required"] else 1):
        if s["required"]:
            params.append(f"{s['pname']}: {s['ptype']}")
        else:
            params.append(f"{s['pname']}: {s['ptype']} = None")

    doc = subparser.description or f"Run WW3Tool command `{command}`."
    doc += (
        f"\n\n执行 `ww3tool {command}`。工作目录 workdir 为含 params.yml 的目录，"
        "建议显式传入；省略时使用 server 进程的当前目录。"
    )
    doc = doc.replace("'''", "'")
    if specs:
        doc += "\n\n参数：\n" + "\n".join(f"- {s['pname']}: {s['help']}" for s in specs)

    body = (
        "def {name}({params}):\n"
        "    '''{doc}'''\n"
        "    return _run_cli({command!r}, _build_argv(locals(), {specs!r}))\n"
    ).format(
        name="tool", params=", ".join(params), doc=doc,
        command=command, specs=specs,
    )

    ns: dict[str, Any] = {"_run_cli": _run_cli, "_build_argv": _build_argv}
    exec(compile(body, f"<mcp tool {tool_name}>", "exec"), ns)
    fn = ns["tool"]
    fn.__name__ = tool_name
    fn.__qualname__ = tool_name
    return fn


def _build_argv(kwargs: dict[str, Any], specs: list[dict[str, Any]]) -> list[str]:
    """按 CLI 约定把 MCP 参数 kwargs 组装为 ``run.py`` 的 argv 片段。"""
    argv: list[str] = []
    for s in specs:
        val = kwargs.get(s["pname"])
        if s["positional"]:
            if val is None:
                continue
            if isinstance(val, (list, tuple)):
                argv.extend(str(v) for v in val)
            else:
                argv.append(str(val))
            continue
        if s["is_flag"]:
            if val:
                argv.append(s["flag"])
            continue
        if val is None:
            continue
        argv.append(s["flag"])
        if isinstance(val, (list, tuple)):
            argv.extend(str(v) for v in val)
        else:
            argv.append(str(val))
    return argv


# ──────────────────────────────────────────────────────────────────────────
# MCP server
# ──────────────────────────────────────────────────────────────────────────

from mcp.server.fastmcp import FastMCP  # noqa: E402

mcp = FastMCP(
    "ww3tool",
    instructions=(
        "WW3Tool（WAVEWATCH III 波浪模拟工作流）的 MCP 接口。"
        "每个 tool 对应一个 CLI 子命令：workdir → validate → run-workflow → local-run"
        "（或 upload --confirm → submit → check-status → download-results），"
        "以及绘图与 Jason-3/NDBC 校验。长任务（local-run / submit）可能耗时较长。"
    ),
)


@mcp.tool()
def list_commands() -> str:
    """列出全部可用的 WW3Tool 子命令及其用途（帮助 LLM 选择工具）。"""
    parser = build_parser()
    sub = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    lines = []
    for name, sp in sorted(sub.choices.items()):
        help_text = (sp.description or "").replace("\n", " ")
        if name == "ssh":
            help_text += "（交互式命令，仅 CLI 使用，MCP 不提供）"
        lines.append(f"{name:20s} {help_text}")
    return "\n".join(lines)


def _register_all_tools() -> None:
    parser = build_parser()
    sub = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    for name, sp in sub.choices.items():
        if name in ("ssh",):
            # 交互式命令（打开 SSH 终端）不适合 MCP 子进程调用，仅 CLI 使用。
            continue
        tool_name = f"{TOOL_PREFIX}_{name.replace('-', '_')}"
        fn = _make_tool(name, sp, tool_name)
        mcp.tool(name=tool_name)(fn)


_register_all_tools()


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
