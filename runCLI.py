#!/usr/bin/env python3
"""WW3Tool 无界面 CLI 入口（实现位于 src2/workflows）。

命令格式
--------
除特殊说明外，每条命令都是::

    python3 runCLI.py <子命令> [选项] <参数文件>

其中 ``<子命令>`` 是下面列出的动词（如 validate、run），
``<参数文件>`` 一般是项目根目录的 ``params.yml``。

不带任何参数直接运行::

    python3 runCLI.py

等价于下面两种情形之一：

- 还没有 ``params.yml`` → 自动生成示例文件，提示你编辑后再运行
- 已有 ``params.yml`` → 自动执行 ``python3 runCLI.py run params.yml``

----------------------------------------------------------------------
一、预处理
----------------------------------------------------------------------

子命令 validate — 校验 params.yml 是否合法
    python3 runCLI.py validate params.yml
    python3 runCLI.py validate params.yml --stage forcing
    python3 runCLI.py validate params.yml --stage grid
    python3 runCLI.py validate params.yml --stage full

子命令 prepare-forcing — 只做 Step 1：准备强迫场（wind.nc 等）
    python3 runCLI.py prepare-forcing params.yml

子命令 generate-grid — 只做 Step 2：生成网格
    python3 runCLI.py generate-grid params.yml
    python3 runCLI.py generate-grid params.yml --no-cache

子命令 run — 完整预处理（强迫场 → 网格 → WW3 namelist）
    python3 runCLI.py run params.yml
    python3 runCLI.py run params.yml --skip-grid
    python3 runCLI.py run params.yml --no-cache

----------------------------------------------------------------------
二、后处理 / 绘图（配置见 params.yml 里的 plot: 段）
----------------------------------------------------------------------

子命令 plot — 执行 plot 段里所有 enabled=true 的任务
    python3 runCLI.py plot params.yml

子命令 plot-wave-maps — 生成波高填色图
    python3 runCLI.py plot-wave-maps params.yml
    python3 runCLI.py plot-wave-maps params.yml --contour

子命令 plot-spectrum — 生成二维方向谱图
    python3 runCLI.py plot-spectrum params.yml
    python3 runCLI.py plot-spectrum params.yml --mode first
    python3 runCLI.py plot-spectrum params.yml --mode all
    python3 runCLI.py plot-spectrum params.yml --mode selected --station 0

子命令 match-jason3 — WW3 结果与 Jason-3 卫星数据匹配
    python3 runCLI.py match-jason3 params.yml

子命令 match-ndbc — WW3 结果与 NDBC 浮标匹配
    python3 runCLI.py match-ndbc params.yml
    python3 runCLI.py match-ndbc params.yml --download

----------------------------------------------------------------------
三、远程运维（配置见 params.yml 里的 server: 段，走 SSH/SLURM）
----------------------------------------------------------------------

子命令 connect-test — 测试能否连上远程服务器
    python3 runCLI.py connect-test params.yml

子命令 list-files — 查看远程工作目录文件列表
    python3 runCLI.py list-files params.yml

子命令 upload — 把本地工作目录上传到远程（必须加 --confirm）
    python3 runCLI.py upload params.yml --confirm

子命令 submit — 在远程执行提交脚本（默认 server.sh）
    python3 runCLI.py submit params.yml
    python3 runCLI.py submit params.yml --script server.sh

子命令 check-status — 检查远程任务是否跑完
    python3 runCLI.py check-status params.yml

子命令 queue-status — 查看 SLURM 队列
    python3 runCLI.py queue-status params.yml

子命令 download-results — 从远程下载 ww3*.nc 结果
    python3 runCLI.py download-results params.yml
    python3 runCLI.py download-results params.yml --nested

子命令 download-log — 从远程下载 success.log / fail.log
    python3 runCLI.py download-log params.yml

子命令 clear-remote — 清空远程工作目录（必须加 --confirm，不可恢复）
    python3 runCLI.py clear-remote params.yml --confirm

子命令 cancel-job — 取消一个 SLURM 任务
    python3 runCLI.py cancel-job params.yml 12345

----------------------------------------------------------------------
四、辅助
----------------------------------------------------------------------

子命令 print-example — 打印示例 params.yml（不需要 params 文件）
    python3 runCLI.py print-example
    python3 runCLI.py print-example > params.yml

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
REQUIREMENTS_FILE = ROOT / "src2" / "requirements.txt"
PARAMS_FILE = ROOT / "params.yml"


def _bootstrap_src2_imports() -> None:
    """将 src2 加入 sys.path，以便 import venv_and_deps、workflows 等模块。"""
    root = ROOT
    for path in (root / "src2",):
        path_str = str(path)
        if path_str not in sys.path:
            sys.path.insert(0, path_str)


def _tr(key: str, default: str) -> str:
    """Translate CLI bootstrap messages after src2 has been added to sys.path."""
    try:
        from workflows.support.translations import tr

        return tr(key, default)
    except Exception:
        return default


def _requires_full_dependencies(argv: list[str]) -> bool:
    """判断当前命令是否需检查虚拟环境与完整依赖（help、print-example 可跳过）。"""
    if not argv:
        return True
    if argv[0] in {"--help", "-h", "print-example"}:
        return False
    if len(argv) >= 2 and argv[1] in {"--help", "-h"}:
        return False
    return True


def _ensure_dependencies() -> None:
    """检查并安装 src2/requirements.txt 中缺失的依赖包。"""
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


def _ensure_params_file() -> bool:
    """若根目录尚无 params.yml，则写入示例配置。

    Returns:
        True 表示刚创建了文件；False 表示文件已存在。
    """
    if PARAMS_FILE.exists():
        print(_tr("cli_params_exists", "参数文件已存在：{path}").format(path=PARAMS_FILE))
        return False
    from workflows.application.configuration import EXAMPLE_YAML

    PARAMS_FILE.write_text(EXAMPLE_YAML, encoding="utf-8")
    print(_tr("cli_params_created", "已创建参数文件：{path}").format(path=PARAMS_FILE))
    return True


def _initialize() -> int:
    """无参启动时的默认行为：创建 params.yml，或自动执行 ``run params.yml``。"""
    try:
        created = _ensure_params_file()
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(_tr("cli_init_failed", "初始化失败：{error}").format(error=exc), file=sys.stderr)
        return 1
    if created:
        print(_tr("cli_edit_params_then_rerun", "请先编辑 params.yml，完成后再次执行：python3 runCLI.py"))
        return 0

    print(_tr("cli_running_default_params", "正在读取默认参数文件并执行流程：{path}").format(path=PARAMS_FILE))
    from workflows.interfaces.command_line import main as run_commands

    return run_commands(["run", str(PARAMS_FILE)])


def main(argv: list[str] | None = None) -> int:
    """CLI 入口：引导 import 路径、按需检查依赖，并分发到 workflows 子命令。"""
    _bootstrap_src2_imports()
    arguments = sys.argv[1:] if argv is None else argv
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
