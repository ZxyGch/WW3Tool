#!/usr/bin/env python3
"""WW3Tool 无界面 CLI 入口（实现位于 src/workflows）。

命令格式
--------
除特殊说明外，每条命令都是::

    python3 runCLI.py <子命令> [选项] [<工作目录>]

其中 ``<子命令>`` 是下面列出的动词（如 validate、run），
``<工作目录>`` 是一个包含 ``params.yml`` 的目录。
**工作目录可省略**，此时自动使用当前目录（``.``）。

**重要**：仓库根目录的 ``params.yml`` 是模板文件，不允许直接用于运行。
请先使用 ``create-workdir`` 创建工作目录副本。

不带任何参数直接运行::

    python3 runCLI.py

若当前目录有 ``params.yml`` → 自动执行 ``run``
若当前目录无 ``params.yml`` → 提示先创建工作目录

----------------------------------------------------------------------
一、工作目录
----------------------------------------------------------------------

子命令 create-workdir — 从根 params.yml 模板创建新工作目录
    python3 runCLI.py create-workdir --name my_case

----------------------------------------------------------------------
二、预处理
----------------------------------------------------------------------

子命令 validate — 校验 params.yml 是否合法
    python3 runCLI.py validate
    python3 runCLI.py validate /path/to/workdir
    python3 runCLI.py validate --stage forcing
    python3 runCLI.py validate --stage grid
    python3 runCLI.py validate --stage full

子命令 prepare-forcing — 只做 Step 1：准备强迫场（wind.nc 等）
    python3 runCLI.py prepare-forcing

子命令 generate-grid — 只做 Step 2：生成网格
    python3 runCLI.py generate-grid
    python3 runCLI.py generate-grid --no-cache

子命令 run — 完整预处理（强迫场 → 网格 → WW3 namelist）
    python3 runCLI.py run
    python3 runCLI.py run /path/to/workdir
    python3 runCLI.py run --skip-grid
    python3 runCLI.py run --no-cache

----------------------------------------------------------------------
三、后处理 / 绘图（配置见 params.yml 里的 plot: 段）
----------------------------------------------------------------------

子命令 plot — 执行 plot 段里所有 enabled=true 的任务
    python3 runCLI.py plot

子命令 plot-wave-maps — 生成波高填色图
    python3 runCLI.py plot-wave-maps
    python3 runCLI.py plot-wave-maps --contour

子命令 plot-spectrum — 生成二维方向谱图
    python3 runCLI.py plot-spectrum
    python3 runCLI.py plot-spectrum --mode first
    python3 runCLI.py plot-spectrum --mode all
    python3 runCLI.py plot-spectrum --mode selected --station 0

子命令 match-jason3 — WW3 结果与 Jason-3 卫星数据匹配
    python3 runCLI.py match-jason3

子命令 match-ndbc — WW3 结果与 NDBC 浮标匹配
    python3 runCLI.py match-ndbc
    python3 runCLI.py match-ndbc --download

----------------------------------------------------------------------
四、远程运维（配置见 params.yml 里的 server: 段，走 SSH/SLURM）
----------------------------------------------------------------------

子命令 connect-test — 测试能否连上远程服务器
    python3 runCLI.py connect-test

子命令 list-files — 查看远程工作目录文件列表
    python3 runCLI.py list-files

子命令 upload — 把本地工作目录上传到远程（必须加 --confirm）
    python3 runCLI.py upload --confirm

子命令 submit — 在远程执行提交脚本（默认 server.sh）
    python3 runCLI.py submit
    python3 runCLI.py submit --script server.sh

子命令 check-status — 检查远程任务是否跑完
    python3 runCLI.py check-status

子命令 queue-status — 查看 SLURM 队列
    python3 runCLI.py queue-status

子命令 download-results — 从远程下载 ww3*.nc 结果
    python3 runCLI.py download-results
    python3 runCLI.py download-results --nested

子命令 download-log — 从远程下载 success.log / fail.log
    python3 runCLI.py download-log

子命令 clear-remote — 清空远程工作目录（必须加 --confirm，不可恢复）
    python3 runCLI.py clear-remote --confirm

子命令 cancel-job — 取消一个 SLURM 任务
    python3 runCLI.py cancel-job 12345

----------------------------------------------------------------------
五、辅助
----------------------------------------------------------------------

子命令 print-example — 打印示例 params.yml（不需要工作目录）
    python3 runCLI.py print-example
    python3 runCLI.py print-example > params.yml

----------------------------------------------------------------------
全局选项
----------------------------------------------------------------------

--lang <语言代码> — 切换输出语言（支持 zh_CN / en_US）
    python3 runCLI.py --lang en_US run
    python3 runCLI.py --lang zh_CN validate
    可放在子命令之前或之后的任意位置。

----------------------------------------------------------------------
退出码
----------------------------------------------------------------------
0  成功
1  运行时异常 / 任务失败
2  参数或 YAML 配置错误
3  破坏性远程操作未加 --confirm
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
ENTRY_SCRIPT = ROOT / "runCLI.py"
REQUIREMENTS_FILE = ROOT / "src" / "requirements.txt"


def _bootstrap_src_imports() -> None:
    """将 src 加入 sys.path，以便 import venv_and_deps、workflows 等模块。"""
    root = ROOT
    for path in (root / "src",):
        path_str = str(path)
        if path_str not in sys.path:
            sys.path.insert(0, path_str)


def _tr(key: str, default: str) -> str:
    """Translate CLI bootstrap messages after src has been added to sys.path."""
    try:
        from workflows.support.translations import tr

        return tr(key, default)
    except Exception:
        return default


def _requires_full_dependencies(argv: list[str]) -> bool:
    """判断当前命令是否需检查虚拟环境与完整依赖（help、print-example、create-workdir 可跳过）。"""
    if not argv:
        return True
    if argv[0] in {"--help", "-h", "print-example", "create-workdir"}:
        return False
    if len(argv) >= 2 and argv[1] in {"--help", "-h"}:
        return False
    return True


def _ensure_dependencies() -> None:
    """检查并安装 src/requirements.txt 中缺失的依赖包。"""
    from venv_and_deps import ensure_dependencies

    ensure_dependencies()


def _ensure_runtime(argv: list[str]) -> None:
    """确保项目虚拟环境存在且当前解释器/依赖满足运行要求。"""
    from venv_and_deps import ensure_runtime

    ensure_runtime(entry_script=ENTRY_SCRIPT, argv=argv)


def _missing_requirements() -> list[str]:
    """返回当前 Python 环境中尚未安装的依赖包名称列表。"""
    from venv_and_deps import missing_requirements

    return missing_requirements()


def _initialize() -> int:
    """无参启动时的默认行为：若当前目录有 params.yml 则自动运行，否则提示用法。"""
    from workflows.interfaces.command_line import main as run_commands

    cwd_params = Path.cwd() / "params.yml"
    if cwd_params.is_file():
        print(_tr("cli_running_cwd_params", "正在读取当前目录参数文件并执行流程：{path}").format(path=cwd_params))
        return run_commands(["run", "."])

    print(_tr(
        "cli_no_workdir_params",
        "当前目录没有 params.yml。\n"
        "请先创建工作目录：\n"
        "  python3 runCLI.py create-workdir --name my_case\n"
        "然后进入工作目录编辑 params.yml 并运行：\n"
        "  cd my_case && python3 runCLI.py run",
    ))
    return 0


def _extract_lang(argv: list[str]) -> tuple[str | None, list[str]]:
    """从参数列表中提取 --lang <code>，返回 (语言代码, 剩余参数)。

    支持 ``--lang en_US`` 和 ``--lang=en_US`` 两种写法。
    若未指定则返回 ``(None, argv)``。
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
    """若指定了 --lang，则调用 set_language 切换输出语言。"""
    if lang is None:
        return
    try:
        from workflows.support.translations import set_language

        set_language(lang)
    except Exception:
        pass


def main(argv: list[str] | None = None) -> int:
    """CLI 入口：引导 import 路径、按需检查依赖，并分发到 workflows 子命令。"""
    _bootstrap_src_imports()
    arguments = sys.argv[1:] if argv is None else argv
    # 提取全局 --lang 选项并切换语言
    lang, arguments = _extract_lang(arguments)
    _apply_language(lang)
    if _requires_full_dependencies(arguments):
        try:
            _ensure_runtime(arguments)
        except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
            print(_tr("cli_dependency_init_failed", "依赖初始化失败：{error}").format(error=exc), file=sys.stderr)
            return 1
    if not arguments:
        return _initialize()
    from workflows.interfaces.command_line import main as run_commands

    return run_commands(arguments)


if __name__ == "__main__":
    raise SystemExit(main())
