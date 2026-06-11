#!/usr/bin/env python3
"""WW3Tool 交互式 CLI 入口（类似 Claude Code / Codex）。

提供 REPL 风格的命令行界面，支持：
- Tab 自动补全命令
- 彩色日志输出
- 内置帮助系统
- 加载/切换 params.yml 配置

用法
----
直接启动（稍后使用 load 命令加载配置）::

    python3 runInteractive.py

启动时自动加载配置::

    python3 runInteractive.py params.yml

可用命令
--------
配置管理：
  load <params.yml>          加载参数配置文件
  config                     显示当前配置摘要

预处理：
  validate                   校验当前配置文件
  prepare-forcing            准备强迫场（Step 1）
  generate-grid [--no-cache] 生成网格（Step 2）
  run [--skip-grid] [--no-cache]  完整预处理流程

后处理 / 绘图：
  plot                       执行所有启用的绘图任务
  plot-wave-maps [--contour] 生成波高填色图或等值线图
  plot-spectrum [--mode first|all|selected] [--station N]  生成方向谱图
  match-jason3               WW3 结果与 Jason-3 卫星数据匹配
  match-ndbc [--download]    WW3 结果与 NDBC 浮标匹配或下载数据

远程运维：
  connect-test               测试 SSH 连接
  list-files                 列出远程工作目录文件
  upload --confirm           上传本地工作目录到远程（需 --confirm）
  submit [--script server.sh] 在远程执行提交脚本
  check-status               检查远程任务状态
  queue-status               查看 SLURM 队列
  download-results [--nested] 下载远程 WW3 结果
  download-log               下载远程日志文件
  clear-remote --confirm     清空远程工作目录（需 --confirm）
  cancel-job <job_id>        取消 SLURM 任务

辅助：
  print-example              打印示例 params.yml
  help / ?                   显示帮助信息
  exit / quit                退出交互式 CLI

----------------------------------------------------------------------
提示
----------------------------------------------------------------------
- 输入命令时按 Tab 键可自动补全
- 破坏性操作（upload / clear-remote）必须加 --confirm 才能执行
- 使用 Ctrl+C 或 Ctrl+D 可随时退出
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def _bootstrap_src2_imports() -> None:
    """将 src2 加入 sys.path，以便 import workflows 模块。"""
    for path in (ROOT / "src2",):
        path_str = str(path)
        if path_str not in sys.path:
            sys.path.insert(0, path_str)


def _ensure_dependencies() -> None:
    """检查并安装 src2/requirements.txt 中缺失的依赖包。"""
    from venv_and_deps import ensure_dependencies
    ensure_dependencies()


def _ensure_runtime(argv: list[str]) -> None:
    """确保项目虚拟环境存在且当前解释器/依赖满足运行要求。"""
    from venv_and_deps import ensure_runtime
    entry_script = ROOT / "runInteractive.py"
    ensure_runtime(entry_script=entry_script, argv=argv)


def main() -> int:
    """交互式 CLI 入口：引导 import 路径、检查依赖并启动 REPL。"""
    _bootstrap_src2_imports()

    # 检查是否需要自动加载 params.yml
    params_path = None
    if len(sys.argv) > 1:
        params_path = sys.argv[1]

    # 确保依赖已安装（help 命令可跳过）
    if params_path and params_path not in {"--help", "-h"}:
        try:
            _ensure_runtime(sys.argv[1:])
        except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
            print(f"依赖初始化失败：{exc}", file=sys.stderr)
            return 1

    # 启动交互式 CLI
    from workflows.interfaces.interactive_cli import main as run_interactive
    return run_interactive(params_path)


if __name__ == "__main__":
    raise SystemExit(main())
