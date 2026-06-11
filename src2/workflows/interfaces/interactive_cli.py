"""交互式 CLI 界面（类似 Claude Code / Codex）。

提供 REPL 风格的命令行界面，支持自动补全、彩色输出和交互式命令执行。
所有命令均委托给 ``application/`` 层的用例函数。

主要特性：
- Tab 自动补全命令名
- 彩色日志输出（ANSI escape codes）
- 内置帮助系统
- 支持加载/切换 params.yml 配置
- 命令执行前显示确认提示（破坏性操作）

主要消费者：
- ``runInteractive.py``：交互式 CLI 入口脚本
"""

from __future__ import annotations

import cmd
import os
import sys
from pathlib import Path
from typing import Optional

from ..application.configuration import ConfigError, EXAMPLE_YAML, load_pipeline_config
from ..domain.config_models import PipelineConfig
from ..support.translations import tr


# ANSI 颜色代码
class _Colors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"


def _color(text: str, color: str) -> str:
    """为文本添加 ANSI 颜色（若终端不支持则原样返回）。"""
    if not sys.stdout.isatty():
        return text
    return f"{color}{text}{_Colors.RESET}"


def _success(text: str) -> str:
    return _color(text, _Colors.GREEN)


def _error(text: str) -> str:
    return _color(text, _Colors.RED)


def _warn(text: str) -> str:
    return _color(text, _Colors.YELLOW)


def _info(text: str) -> str:
    return _color(text, _Colors.CYAN)


def _bold(text: str) -> str:
    return _color(text, _Colors.BOLD)


class InteractiveCLI(cmd.Cmd):
    """交互式 WW3Tool CLI，提供 REPL 界面调用 workflows 用例。"""

    intro = _bold("\n🌊 WW3Tool 交互式命令行界面") + "\n输入 'help' 或 '?' 查看可用命令，输入 'exit' 退出。\n"
    prompt = _color("ww3> ", _Colors.BLUE)

    def __init__(self, params_path: Optional[str] = None):
        super().__init__()
        self._config: Optional[PipelineConfig] = None
        self._params_path: Optional[Path] = None
        if params_path:
            self._load_config(params_path)

    def parseline(self, line: str) -> tuple[str | None, str | None, str]:
        """重写行解析：支持含 '-' 的命令名（如 prepare-forcing → do_prepare_forcing）。"""
        stripped = line.strip()
        if not stripped:
            return None, None, line
        # 提取第一个 token（命令名），将其中的 '-' 替换为 '_'
        parts = stripped.split(None, 1)
        cmd_name = parts[0].replace("-", "_")
        arg = parts[1] if len(parts) > 1 else ""
        # 检查是否对应已注册的 do_xxx 方法
        if hasattr(self, f"do_{cmd_name}"):
            return cmd_name, arg, line
        # 回退到默认解析（处理 help、? 等内置命令）
        return super().parseline(line)

    def _load_config(self, path: str) -> bool:
        """加载或重新加载 params.yml 配置文件。"""
        try:
            source = Path(path).expanduser().resolve()
            self._config = load_pipeline_config(str(source), validation_stage="plot")
            self._params_path = source
            print(_success(f"✓ 已加载配置：{source}"))
            return True
        except ConfigError as exc:
            print(_error(f"✗ 配置错误：{exc}"))
            return False
        except Exception as exc:
            print(_error(f"✗ 加载失败：{exc}"))
            return False

    def _require_config(self) -> bool:
        """检查是否已加载配置，未加载时提示用户。"""
        if self._config is None:
            print(_warn("⚠ 未加载配置文件，请先使用 'load <params.yml>' 加载参数"))
            return False
        return True

    def _log_callback(self, message: str) -> None:
        """日志回调函数，实时输出到终端。"""
        print(message)

    # ── 配置管理命令 ─────────────────────────────────────────────────────

    def do_load(self, arg: str) -> None:
        """load <params.yml>  — 加载参数配置文件"""
        if not arg.strip():
            print(_warn("用法：load <params.yml 路径>"))
            return
        self._load_config(arg.strip())

    def do_config(self, arg: str) -> None:
        """config  — 显示当前配置摘要"""
        if not self._require_config():
            return
        cfg = self._config
        print(_bold("\n📋 当前配置摘要"))
        print(f"  配置文件：{self._params_path}")
        print(f"  工作目录：{cfg.workdir.path}")
        print(f"  网格类型：{cfg.grid.mesh_type} / {cfg.grid.grid_type}")
        print(f"  强迫场：")
        print(f"    风场：{cfg.forcing.wind or '(未设置)'}")
        print(f"    流场：{cfg.forcing.current or '(未设置)'}")
        print(f"    水位：{cfg.forcing.level or '(未设置)'}")
        print(f"  WW3 时段：{cfg.ww3.start_date} ~ {cfg.ww3.end_date}")
        print(f"  服务器：{cfg.server.host or '(未配置)'}")
        print()

    # ── 预处理命令 ─────────────────────────────────────────────────────────

    def do_validate(self, arg: str) -> None:
        """validate  — 校验当前配置文件"""
        if not self._require_config():
            return
        try:
            load_pipeline_config(str(self._params_path), validation_stage="full")
            print(_success("✓ 配置文件校验通过"))
        except ConfigError as exc:
            print(_error(f"✗ 校验失败：{exc}"))

    def do_prepare_forcing(self, arg: str) -> None:
        """prepare-forcing  — 准备强迫场（Step 1）"""
        if not self._require_config():
            return
        try:
            from ..application.preprocessing_workflow import run_prepare_forcing
            print(_info("▶ 开始准备强迫场..."))
            run_prepare_forcing(self._config, log=self._log_callback)
            print(_success("✓ 强迫场准备完成"))
        except Exception as exc:
            print(_error(f"✗ 执行失败：{exc}"))

    def do_generate_grid(self, arg: str) -> None:
        """generate-grid [--no-cache]  — 生成网格（Step 2）"""
        if not self._require_config():
            return
        use_cache = "--no-cache" not in arg
        try:
            from ..application.grid_preparation import run_generate_grid
            print(_info("▶ 开始生成网格..."))
            run_generate_grid(self._config, log=self._log_callback, use_cache=use_cache)
            print(_success("✓ 网格生成完成"))
        except Exception as exc:
            print(_error(f"✗ 执行失败：{exc}"))

    def do_run(self, arg: str) -> None:
        """run [--skip-grid] [--no-cache]  — 完整预处理流程"""
        if not self._require_config():
            return
        skip_grid = "--skip-grid" in arg
        use_cache = "--no-cache" not in arg
        try:
            from ..application.preprocessing_workflow import run_pipeline
            print(_info("▶ 开始完整预处理..."))
            run_pipeline(
                self._config,
                log=self._log_callback,
                skip_grid=skip_grid,
                use_grid_cache=use_cache,
            )
            print(_success("✓ 预处理完成"))
        except Exception as exc:
            print(_error(f"✗ 执行失败：{exc}"))

    # ── 后处理 / 绘图命令 ──────────────────────────────────────────────────

    def do_plot(self, arg: str) -> None:
        """plot  — 执行所有启用的绘图任务"""
        if not self._require_config():
            return
        try:
            from .command_line import _run_all_plots
            print(_info("▶ 开始执行绘图任务..."))
            rc = _run_all_plots(self._config)
            if rc == 0:
                print(_success("✓ 绘图任务完成"))
            else:
                print(_warn("⚠ 部分绘图任务失败"))
        except Exception as exc:
            print(_error(f"✗ 执行失败：{exc}"))

    def do_plot_wave_maps(self, arg: str) -> None:
        """plot-wave-maps [--contour]  — 生成波高填色图或等值线图"""
        if not self._require_config():
            return
        contour = "--contour" in arg
        try:
            from .command_line import _run_wave_maps
            print(_info("▶ 开始生成波高图..."))
            rc = _run_wave_maps(self._config, contour=contour)
            if rc == 0:
                print(_success("✓ 波高图生成完成"))
            else:
                print(_error("✗ 波高图生成失败"))
        except Exception as exc:
            print(_error(f"✗ 执行失败：{exc}"))

    def do_plot_spectrum(self, arg: str) -> None:
        """plot-spectrum [--mode first|all|selected] [--station N]  — 生成方向谱图"""
        if not self._require_config():
            return
        mode = "all"
        station = 0
        parts = arg.split()
        for i, part in enumerate(parts):
            if part == "--mode" and i + 1 < len(parts):
                mode = parts[i + 1]
            elif part == "--station" and i + 1 < len(parts):
                station = int(parts[i + 1])
        try:
            from .command_line import _run_spectrum
            print(_info("▶ 开始生成方向谱图..."))
            rc = _run_spectrum(self._config, mode=mode, station_index=station)
            if rc == 0:
                print(_success("✓ 方向谱图生成完成"))
            else:
                print(_error("✗ 方向谱图生成失败"))
        except Exception as exc:
            print(_error(f"✗ 执行失败：{exc}"))

    def do_match_jason3(self, arg: str) -> None:
        """match-jason3  — WW3 结果与 Jason-3 卫星数据匹配"""
        if not self._require_config():
            return
        try:
            from .command_line import _run_match_jason3
            print(_info("▶ 开始 Jason-3 匹配..."))
            rc = _run_match_jason3(self._config)
            if rc == 0:
                print(_success("✓ Jason-3 匹配完成"))
            else:
                print(_error("✗ Jason-3 匹配失败"))
        except Exception as exc:
            print(_error(f"✗ 执行失败：{exc}"))

    def do_jason3_swh(self, arg: str) -> None:
        """jason3-swh  — 绘制 Jason-3 卫星 SWH / 轨迹图"""
        if not self._require_config():
            return
        try:
            from .command_line import _run_jason3_swh
            print(_info("▶ 开始生成 Jason-3 卫星观测图..."))
            rc = _run_jason3_swh(self._config)
            if rc == 0:
                print(_success("✓ Jason-3 卫星观测图生成完成"))
            else:
                print(_error("✗ Jason-3 卫星观测图生成失败"))
        except Exception as exc:
            print(_error(f"✗ 执行失败：{exc}"))

    def do_download_jason3(self, arg: str) -> None:
        """download-jason3  — 下载 Jason-3 L2 数据"""
        if not self._require_config():
            return
        try:
            from .command_line import _run_download_jason3
            print(_info("▶ 开始下载 Jason-3 数据..."))
            rc = _run_download_jason3(self._config)
            if rc == 0:
                print(_success("✓ Jason-3 数据下载完成"))
            else:
                print(_error("✗ Jason-3 数据下载失败"))
        except Exception as exc:
            print(_error(f"✗ 执行失败：{exc}"))

    def do_match_ndbc(self, arg: str) -> None:
        """match-ndbc [--download]  — WW3 结果与 NDBC 浮标匹配或下载数据"""
        if not self._require_config():
            return
        download = "--download" in arg
        try:
            from .command_line import _run_match_ndbc
            print(_info("▶ 开始 NDBC 处理..."))
            rc = _run_match_ndbc(self._config, download=download)
            if rc == 0:
                print(_success("✓ NDBC 处理完成"))
            else:
                print(_error("✗ NDBC 处理失败"))
        except Exception as exc:
            print(_error(f"✗ 执行失败：{exc}"))

    # ── 远程运维命令 ───────────────────────────────────────────────────────

    def do_connect_test(self, arg: str) -> None:
        """connect-test  — 测试 SSH 连接"""
        if not self._require_config():
            return
        try:
            from ..application.remote_ops import run_connect_test
            print(_info("▶ 测试连接..."))
            result = run_connect_test(self._config, log=self._log_callback)
            if result.success:
                print(_success("✓ 连接成功"))
            else:
                print(_error(f"✗ 连接失败：{result.error}"))
        except Exception as exc:
            print(_error(f"✗ 执行失败：{exc}"))

    def do_list_files(self, arg: str) -> None:
        """list-files  — 列出远程工作目录文件"""
        if not self._require_config():
            return
        try:
            from ..application.remote_ops import run_list_files
            print(_info("▶ 获取文件列表..."))
            result = run_list_files(self._config, log=self._log_callback)
            if not result.success:
                print(_error(f"✗ 获取失败：{result.error}"))
        except Exception as exc:
            print(_error(f"✗ 执行失败：{exc}"))

    def do_upload(self, arg: str) -> None:
        """upload --confirm  — 上传本地工作目录到远程（需 --confirm）"""
        if not self._require_config():
            return
        if "--confirm" not in arg:
            print(_warn("⚠ upload 是破坏性操作，必须加 --confirm 才能执行"))
            print(_warn("  用法：upload --confirm"))
            return
        try:
            from ..application.remote_ops import run_upload
            print(_info("▶ 开始上传..."))
            result = run_upload(self._config, log=self._log_callback, confirmed=True)
            if result.success:
                print(_success("✓ 上传完成"))
            else:
                print(_error(f"✗ 上传失败：{result.error}"))
        except Exception as exc:
            print(_error(f"✗ 执行失败：{exc}"))

    def do_submit(self, arg: str) -> None:
        """submit [--script server.sh]  — 在远程执行提交脚本"""
        if not self._require_config():
            return
        script = "server.sh"
        parts = arg.split()
        for i, part in enumerate(parts):
            if part == "--script" and i + 1 < len(parts):
                script = parts[i + 1]
        try:
            from ..application.remote_ops import run_submit
            print(_info(f"▶ 执行远程脚本：{script}..."))
            result = run_submit(self._config, log=self._log_callback, script=script)
            if result.success:
                print(_success("✓ 脚本执行完成"))
            else:
                print(_error(f"✗ 脚本执行失败：{result.error}"))
        except Exception as exc:
            print(_error(f"✗ 执行失败：{exc}"))

    def do_check_status(self, arg: str) -> None:
        """check-status  — 检查远程任务状态"""
        if not self._require_config():
            return
        try:
            from ..application.remote_ops import run_check_status
            print(_info("▶ 检查状态..."))
            result = run_check_status(self._config, log=self._log_callback)
            if not result.success:
                print(_error(f"✗ 检查失败：{result.error}"))
        except Exception as exc:
            print(_error(f"✗ 执行失败：{exc}"))

    def do_queue_status(self, arg: str) -> None:
        """queue-status  — 查看 SLURM 队列"""
        if not self._require_config():
            return
        try:
            from ..application.remote_ops import run_queue_status
            print(_info("▶ 获取队列状态..."))
            result = run_queue_status(self._config, log=self._log_callback)
            if not result.success:
                print(_error(f"✗ 获取失败：{result.error}"))
        except Exception as exc:
            print(_error(f"✗ 执行失败：{exc}"))

    def do_download_results(self, arg: str) -> None:
        """download-results [--nested]  — 下载远程 WW3 结果"""
        if not self._require_config():
            return
        nested = "--nested" in arg
        try:
            from ..application.remote_ops import run_download_results
            print(_info("▶ 下载结果文件..."))
            result = run_download_results(self._config, log=self._log_callback, nested=nested)
            if result.success:
                print(_success("✓ 下载完成"))
            else:
                print(_error(f"✗ 下载失败：{result.error}"))
        except Exception as exc:
            print(_error(f"✗ 执行失败：{exc}"))

    def do_download_log(self, arg: str) -> None:
        """download-log  — 下载远程日志文件"""
        if not self._require_config():
            return
        try:
            from ..application.remote_ops import run_download_log
            print(_info("▶ 下载日志..."))
            result = run_download_log(self._config, log=self._log_callback)
            if result.success:
                print(_success("✓ 日志下载完成"))
            else:
                print(_error(f"✗ 日志下载失败：{result.error}"))
        except Exception as exc:
            print(_error(f"✗ 执行失败：{exc}"))

    def do_clear_remote(self, arg: str) -> None:
        """clear-remote --confirm  — 清空远程工作目录（需 --confirm）"""
        if not self._require_config():
            return
        if "--confirm" not in arg:
            print(_warn("⚠ clear-remote 是破坏性操作，必须加 --confirm 才能执行"))
            print(_warn("  用法：clear-remote --confirm"))
            return
        try:
            from ..application.remote_ops import run_clear_remote
            print(_info("▶ 清空远程目录..."))
            result = run_clear_remote(self._config, log=self._log_callback, confirmed=True)
            if result.success:
                print(_success("✓ 远程目录已清空"))
            else:
                print(_error(f"✗ 清空失败：{result.error}"))
        except Exception as exc:
            print(_error(f"✗ 执行失败：{exc}"))

    def do_cancel_job(self, arg: str) -> None:
        """cancel-job <job_id>  — 取消 SLURM 任务"""
        if not self._require_config():
            return
        job_id = arg.strip()
        if not job_id:
            print(_warn("用法：cancel-job <job_id>"))
            return
        try:
            from ..application.remote_ops import run_cancel_job
            print(_info(f"▶ 取消任务 {job_id}..."))
            result = run_cancel_job(self._config, job_id, log=self._log_callback)
            if result.success:
                print(_success("✓ 任务已取消"))
            else:
                print(_error(f"✗ 取消失败：{result.error}"))
        except Exception as exc:
            print(_error(f"✗ 执行失败：{exc}"))

    # ── 辅助命令 ───────────────────────────────────────────────────────────

    def do_print_example(self, arg: str) -> None:
        """print-example  — 打印示例 params.yml"""
        print(EXAMPLE_YAML)

    def do_exit(self, arg: str) -> bool:
        """exit  — 退出交互式 CLI"""
        print(_info("👋 再见！"))
        return True

    def do_quit(self, arg: str) -> bool:
        """quit  — 退出交互式 CLI"""
        return self.do_exit(arg)

    def do_EOF(self, arg: str) -> bool:
        """处理 Ctrl+D"""
        print()
        return self.do_exit(arg)

    # ── 自动补全支持 ───────────────────────────────────────────────────────

    def complete_load(self, text: str, line: str, begidx: int, endidx: int) -> list[str]:
        """Tab 补全文件路径"""
        if not text:
            return [str(p) for p in Path(".").glob("*.yml")]
        return [str(p) for p in Path(text).parent.glob(f"{Path(text).name}*.yml")]

    # 为所有命令添加通用补全（参数选项）
    def _complete_options(self, text: str, options: list[str]) -> list[str]:
        return [opt for opt in options if opt.startswith(text)]

    def complete_generate_grid(self, text: str, line: str, begidx: int, endidx: int) -> list[str]:
        return self._complete_options(text, ["--no-cache"])

    def complete_run(self, text: str, line: str, begidx: int, endidx: int) -> list[str]:
        return self._complete_options(text, ["--skip-grid", "--no-cache"])

    def complete_plot_wave_maps(self, text: str, line: str, begidx: int, endidx: int) -> list[str]:
        return self._complete_options(text, ["--contour"])

    def complete_plot_spectrum(self, text: str, line: str, begidx: int, endidx: int) -> list[str]:
        return self._complete_options(text, ["--mode", "--station"])

    def complete_match_ndbc(self, text: str, line: str, begidx: int, endidx: int) -> list[str]:
        return self._complete_options(text, ["--download"])

    def complete_upload(self, text: str, line: str, begidx: int, endidx: int) -> list[str]:
        return self._complete_options(text, ["--confirm"])

    def complete_submit(self, text: str, line: str, begidx: int, endidx: int) -> list[str]:
        return self._complete_options(text, ["--script"])

    def complete_download_results(self, text: str, line: str, begidx: int, endidx: int) -> list[str]:
        return self._complete_options(text, ["--nested"])

    def complete_clear_remote(self, text: str, line: str, begidx: int, endidx: int) -> list[str]:
        return self._complete_options(text, ["--confirm"])


def main(params_path: Optional[str] = None) -> int:
    """交互式 CLI 主入口。

    Args:
        params_path: 可选，启动时自动加载的 params.yml 路径。

    Returns:
        退出码（始终为 0）。
    """
    cli = InteractiveCLI(params_path)
    try:
        cli.cmdloop()
    except KeyboardInterrupt:
        print(_info("\n👋 再见！"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
