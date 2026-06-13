#!/usr/bin/env python3
"""WW3Tool 统一入口（实现位于 src/）。

一个入口通吃三种使用方式，并统一负责环境搭建（虚拟环境 / 依赖 / sys.path）：

    python3 run.py                       → 启动 Desktop 图形界面（默认）
    python3 run.py shell [params]        → 启动交互式 REPL（可选带 params.yml）
    python3 run.py <子命令> [选项] [工作目录]  → 无界面 CLI

内部委派关系（均为进程内 import 调用）：

    无参          → desktop.application.main
    shell         → workflows.interfaces.interactive_cli.main
    其它子命令     → workflows.interfaces.command_line.main

----------------------------------------------------------------------
无界面 CLI 子命令
----------------------------------------------------------------------

**重要**：仓库根目录的 ``params.yml`` 是模板文件，不允许直接用于运行。
请先使用 ``create-workdir`` 创建工作目录副本。``<工作目录>`` 可省略，
此时使用当前目录（``.``）。

一、工作目录
  create-workdir --name my_case   从根 params.yml 模板创建新工作目录

二、预处理
  validate [--stage forcing|grid|full]   校验 params.yml 是否合法
  prepare-forcing                        只做 Step 1：准备强迫场（wind.nc 等）
  generate-grid [--no-cache]             只做 Step 2：生成网格
  run [--skip-grid] [--no-cache]         完整预处理（强迫场 → 网格 → WW3 namelist）

三、后处理 / 绘图（配置见 params.yml 的 plot: 段）
  plot                                   执行 plot 段里所有 enabled=true 的任务
  plot-wave-maps [--contour]             生成波高填色图 / 等值线图
  plot-spectrum [--mode first|all|selected] [--station N]   生成二维方向谱图
  plot-jason3                            WW3 结果与 Jason-3 卫星数据匹配
  plot-ndbc [--download]                 WW3 结果与 NDBC 浮标匹配

四、远程运维（配置见 params.yml 的 server: 段，走 SSH/SLURM）
  connect-test / list-files / upload --confirm / submit [--script server.sh]
  check-status / queue-status / download-results [--nested] / download-log
  clear-remote --confirm / cancel-job <job_id>

五、辅助
  print-example                          打印示例 params.yml（不需要工作目录）

----------------------------------------------------------------------
全局选项
----------------------------------------------------------------------
--lang <语言代码>   切换输出语言（支持 zh_CN / en_US），可放在任意位置。

----------------------------------------------------------------------
退出码
----------------------------------------------------------------------
0  成功
1  运行时异常 / 任务失败 / 依赖初始化失败
2  参数或 YAML 配置错误
3  破坏性远程操作未加 --confirm

[EN] Unified WW3Tool entry point (implementation lives in src/).

One entry point for three usage modes, and the single place responsible for
runtime setup (venv / dependencies / sys.path):

    python3 run.py                       -> Launch the Desktop GUI (default)
    python3 run.py shell [params]        -> Launch the interactive REPL (optional params.yml)
    python3 run.py <subcommand> [opts] [workdir]  -> Headless CLI

Internal delegation (all in-process import calls):

    no args       -> desktop.application.main
    shell         -> workflows.interfaces.interactive_cli.main
    other commands-> workflows.interfaces.command_line.main

----------------------------------------------------------------------
Headless CLI subcommands
----------------------------------------------------------------------

**Important**: The repository-root ``params.yml`` is a template file and must
not be run directly. Create a working-directory copy with ``create-workdir``
first. ``<workdir>`` may be omitted, in which case the current directory
(``.``) is used.

1. Working directory
  create-workdir --name my_case   Create a new workdir from the root params.yml template

2. Preprocessing
  validate [--stage forcing|grid|full]   Validate whether params.yml is legal
  prepare-forcing                        Step 1 only: prepare forcing fields (wind.nc etc.)
  generate-grid [--no-cache]             Step 2 only: generate the grid
  run [--skip-grid] [--no-cache]         Full preprocessing (forcing -> grid -> WW3 namelist)

3. Post-processing / plotting (configured in the plot: section of params.yml)
  plot                                   Run all enabled=true tasks in the plot section
  plot-wave-maps [--contour]             Generate wave-height filled-color / contour maps
  plot-spectrum [--mode first|all|selected] [--station N]   Generate 2-D directional spectrum plots
  plot-jason3                            Match WW3 results with Jason-3 satellite data
  plot-ndbc [--download]                 Match WW3 results with NDBC buoys

4. Remote operations (configured in the server: section of params.yml, via SSH/SLURM)
  connect-test / list-files / upload --confirm / submit [--script server.sh]
  check-status / queue-status / download-results [--nested] / download-log
  clear-remote --confirm / cancel-job <job_id>

5. Auxiliary
  print-example                          Print an example params.yml (no workdir needed)

----------------------------------------------------------------------
Global options
----------------------------------------------------------------------
--lang <code>   Switch output language (supports zh_CN / en_US); may appear anywhere.

----------------------------------------------------------------------
Exit codes
----------------------------------------------------------------------
0  Success
1  Runtime exception / task failure / dependency initialization failure
2  Parameter or YAML configuration error
3  Destructive remote operation without --confirm
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
ENTRY_SCRIPT = ROOT / "run.py"

# 无需完整虚拟环境/依赖即可执行的轻量 CLI 子命令。
# [EN] Lightweight CLI subcommands that don't require the full venv/dependencies.
_LIGHT_CLI_COMMANDS = {"--help", "-h", "print-example", "create-workdir"}


def _bootstrap_src_imports() -> None:
    """将 src 加入 sys.path，以便 import venv_and_deps、workflows、desktop 等模块。

    [EN] Add src to sys.path so venv_and_deps, workflows and desktop can be imported.
    """
    src_str = str(ROOT / "src")
    if src_str not in sys.path:
        sys.path.insert(0, src_str)


def _tr(key: str, default: str) -> str:
    """Translate bootstrap messages after src has been added to sys.path."""
    try:
        from workflows.support.translations import tr

        return tr(key, default)
    except Exception:
        return default


def _extract_lang(argv: list[str]) -> tuple[str | None, list[str]]:
    """从参数列表中提取 ``--lang <code>``，返回 ``(语言代码, 剩余参数)``。

    支持 ``--lang en_US`` 与 ``--lang=en_US`` 两种写法；未指定则返回 ``(None, argv)``。

    [EN] Extract ``--lang <code>`` from the argument list, returning
    ``(language code, remaining args)``. Supports both ``--lang en_US`` and
    ``--lang=en_US`` forms; returns ``(None, argv)`` if not specified.
    """
    lang: str | None = None
    remaining: list[str] = []
    skip_next = False
    for i, arg in enumerate(argv):
        if skip_next:
            skip_next = False
            continue
        if arg == "--lang":
            if i + 1 < len(argv):
                lang = argv[i + 1]
                skip_next = True
            continue
        if arg.startswith("--lang="):
            lang = arg.split("=", 1)[1]
            continue
        remaining.append(arg)
    return lang, remaining


def _apply_language(lang: str | None) -> None:
    """若指定了 ``--lang``，则调用 set_language 切换输出语言。

    [EN] If ``--lang`` is specified, call set_language to switch output language.
    """
    if lang is None:
        return
    try:
        from workflows.support.translations import set_language

        set_language(lang)
    except Exception:
        pass


def _requires_full_dependencies(mode: str, rest: list[str]) -> bool:
    """判断当前调用是否需要检查虚拟环境与完整依赖。

    Desktop 与 interactive 始终需要完整依赖；CLI 下的 help / print-example /
    create-workdir 可跳过。

    [EN] Whether the current invocation needs the full venv/dependency check.
    Desktop and interactive always do; for the CLI, help / print-example /
    create-workdir can be skipped.
    """
    if mode != "cli":
        return True
    if not rest:
        return True
    if rest[0] in _LIGHT_CLI_COMMANDS:
        return False
    if len(rest) >= 2 and rest[1] in {"--help", "-h"}:
        return False
    return True


def main(argv: list[str] | None = None) -> int:
    """统一入口：引导 import 路径、按需检查依赖，并按模式分发。

    [EN] Unified entry point: bootstrap import paths, check dependencies as
    needed, and dispatch by mode.
    """
    _bootstrap_src_imports()
    # 保留 --lang 在原始 argv 中，使 ensure_runtime re-exec 后的新进程也能读取语言设置。
    # [EN] Keep --lang in the original argv so it survives ensure_runtime's re-exec.
    original = sys.argv[1:] if argv is None else list(argv)
    lang, rest = _extract_lang(original)
    _apply_language(lang)

    if not rest:
        mode = "desktop"
    elif rest[0] == "shell":
        mode = "shell"
    else:
        mode = "cli"

    if _requires_full_dependencies(mode, rest):
        from venv_and_deps import ensure_runtime

        try:
            ensure_runtime(entry_script=ENTRY_SCRIPT, argv=original)
        except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
            print(
                _tr("cli_dependency_init_failed", "依赖初始化失败：{error}").format(error=exc),
                file=sys.stderr,
            )
            return 1

    if mode == "desktop":
        from desktop.application import main as run_desktop

        return run_desktop([])

    if mode == "shell":
        from workflows.interfaces.interactive_cli import main as run_interactive

        params_path = rest[1] if len(rest) > 1 and rest[1] not in {"--help", "-h"} else None
        return run_interactive(params_path)

    from workflows.interfaces.command_line import main as run_commands

    return run_commands(rest)


if __name__ == "__main__":
    raise SystemExit(main())
