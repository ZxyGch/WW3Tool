"""交互式 CLI 界面（类似 Claude Code / Codex）。

提供 REPL 风格的命令行界面，支持自动补全、彩色输出和交互式命令执行。
所有命令均委托给 ``application/`` 层的用例函数。

主要特性：
- Tab 自动补全命令
- 彩色日志输出（ANSI escape codes）
- 内置帮助系统
- 支持加载/切换 params.yml 配置
- 命令执行前显示确认提示（破坏性操作）
- 多语言支持（通过 tr() 翻译函数）

主要消费者：
- ``run.py shell``：交互式 CLI 入口（根目录 run.py 的 shell 子命令）

[EN] Interactive CLI interface (similar to Claude Code / Codex).

Provides a REPL-style command-line interface with auto-completion, colored output,
and interactive command execution. All commands are delegated to use-case functions
in the ``application/`` layer.

Main features:
- Tab auto-completion for commands
- Colored log output (ANSI escape codes)
- Built-in help system
- Support for loading/switching params.yml configurations
- Confirmation prompts before destructive operations
- Multi-language support (via tr() translation function)

Main consumers:
- ``run.py shell``: interactive CLI entry (the shell subcommand of root run.py)
"""

from __future__ import annotations

import cmd
import os
import readline
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

from ..application.configuration import ConfigError, EXAMPLE_YAML, load_pipeline_config
from ..domain.config_models import PipelineConfig
from ..support.translations import tr


# ANSI 颜色代码
# [EN] ANSI color codes
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
    """为文本添加 ANSI 颜色（若终端不支持则原样返回）。

    [EN] Add ANSI color to text (return as-is if terminal does not support it).
    """
    if not sys.stdout.isatty():
        return text
    return f"{color}{text}{_Colors.RESET}"


def _rl_prompt(text: str, color: str) -> str:
    """为 readline 提示符添加 ANSI 颜色，用 \\001/\\002 标记不可见字符。

    [EN] Add ANSI color to a readline prompt, using \\001/\\002 to mark non-visible characters.
    """
    if not sys.stdout.isatty():
        return text
    return f"\001{color}\002{text}\001{_Colors.RESET}\002"


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


_HISTORY_FILE = Path.home() / ".ww3tool_history"
_HISTORY_MAX_LINES = 500


def _help_groups() -> list[tuple[str, list[tuple[str, str]]]]:
    """构建帮助分组（运行时调用 tr()，确保语言切换后即时生效）。

    [EN] Build help groups (calls tr() at runtime so language switches take effect immediately).
    """
    return [
        (
            tr("icli_grp_config", "配置管理"),
            [
                ("load <params.yml>", tr("icli_help_load", "加载参数配置文件")),
                ("config", tr("icli_help_config", "显示当前配置摘要")),
                ("print", tr("icli_help_print", "输出当前 params.yml 内容")),
            ],
        ),
        (
            tr("icli_grp_preproc", "预处理"),
            [
                ("create-workdir <name>", tr("icli_help_create_workdir", "从模板创建新工作目录")),
                ("validate [--stage forcing|grid|full]", tr("icli_help_validate", "校验当前配置文件")),
                ("prepare-forcing", tr("icli_help_prepare_forcing", "准备强迫场（Step 1）")),
                ("generate-grid [--no-cache]", tr("icli_help_generate_grid", "生成网格（Step 2）")),
                ("prepare-ww3", tr("icli_help_prepare_ww3", "仅生成 WW3 namelist（不重跑强迫场和网格）")),
                ("run-pre-workflow [--skip-grid] [--no-cache]", tr("icli_help_run", "完整预处理流程")),
            ],
        ),
        (
            tr("icli_grp_plot", "后处理 / 绘图"),
            [
                ("plot-wave-maps [--contour]", tr("icli_help_plot_wave_maps", "生成波高填色图或等值线图")),
                ("plot-spectrum [--mode ...] [--station N]", tr("icli_help_plot_spectrum", "生成方向谱图")),
                ("plot-jason3", tr("icli_help_match_jason3", "WW3 结果与 Jason-3 卫星数据匹配")),
                ("plot-jason3-swh", tr("icli_help_jason3_swh", "绘制 Jason-3 卫星 SWH / 轨迹图")),
                ("download-jason3", tr("icli_help_download_jason3", "下载 Jason-3 L2 数据")),
                ("plot-ndbc [--download]", tr("icli_help_match_ndbc", "WW3 结果与 NDBC 浮标匹配")),
            ],
        ),
        (
            tr("icli_grp_remote", "远程运维"),
            [
                ("connect-test", tr("icli_help_connect_test", "测试 SSH 连接")),
                ("ssh", tr("icli_help_ssh", "打开交互式 SSH 终端")),
                ("list-files", tr("icli_help_list_files", "列出远程工作目录文件")),
                ("upload --confirm", tr("icli_help_upload", "上传本地工作目录到远程")),
                ("submit [--script server.sh]", tr("icli_help_submit", "在远程执行提交脚本")),
                ("check-status", tr("icli_help_check_status", "检查远程任务状态")),
                ("queue-status", tr("icli_help_queue_status", "查看 SLURM 队列")),
                ("download-results [--nested]", tr("icli_help_download_results", "下载远程 WW3 结果")),
                ("download-log", tr("icli_help_download_log", "下载远程日志文件")),
                ("clear-remote --confirm", tr("icli_help_clear_remote", "清空远程工作目录")),
                ("cancel-job <job_id>", tr("icli_help_cancel_job", "取消 SLURM 任务")),
            ],
        ),
        (
            tr("icli_grp_aux", "辅助"),
            [
                ("print-example", tr("icli_help_print_example", "打印示例 params.yml")),
                ("help / ?", tr("icli_help_help", "显示帮助信息")),
                ("exit / quit", tr("icli_help_exit", "退出交互式 CLI")),
            ],
        ),
    ]


class InteractiveCLI(cmd.Cmd):
    """交互式 WW3Tool CLI，提供 REPL 界面调用 workflows 用例。

    [EN] Interactive WW3Tool CLI providing a REPL interface for invoking workflow use cases.
    """

    prompt = _rl_prompt("ww3> ", _Colors.BLUE)

    def __init__(self, params_path: Optional[str] = None):
        super().__init__()
        self._config: Optional[PipelineConfig] = None
        self._params_path: Optional[Path] = None
        if params_path:
            self._load_config(params_path)

    @property
    def intro(self) -> str:
        """动态生成欢迎语，确保语言切换后即时生效。

        [EN] Dynamically generate the welcome message so language switches take effect immediately.
        """
        return (
            _bold(tr("icli_intro", "\n🌊 WW3Tool 交互式命令行界面"))
            + "\n"
            + tr("icli_intro_hint", "输入 'help' 或 '?' 查看可用命令，输入 'exit' 退出。")
            + "\n"
        )

    # ── 历史记录持久化 ───────────────────────────────────────────────────
    # [EN] ── History persistence ──────────────────────────────────────────

    def preloop(self) -> None:
        """启动时加载历史命令文件。

        [EN] Load command history file on startup.
        """
        try:
            readline.read_history_file(str(_HISTORY_FILE))
        except FileNotFoundError:
            pass
        readline.set_history_length(_HISTORY_MAX_LINES)

    def postloop(self) -> None:
        """退出时保存历史命令文件。

        [EN] Save command history file on exit.
        """
        try:
            readline.write_history_file(str(_HISTORY_FILE))
        except OSError:
            pass

    # ── 美化帮助 ──────────────────────────────────────────────────────────
    # [EN] ── Pretty help ─────────────────────────────────────────────────

    def do_help(self, arg: str) -> None:
        """显示分组彩色帮助信息。

        [EN] Display grouped colored help information.
        """
        if arg:
            # 单条命令帮助：解析 docstring 并翻译描述部分
            # [EN] Single command help: parse docstring and translate the description part
            cmd_name = arg.strip().replace("-", "_")
            method = getattr(self, f"do_{cmd_name}", None)
            if method and method.__doc__:
                doc = method.__doc__
                # docstring 格式: "command [opts]  — 描述"
                # [EN] docstring format: "command [opts]  — description"
                if " — " in doc:
                    prefix, desc = doc.split(" — ", 1)
                    # 在帮助分组中查找对应的翻译键
                    # [EN] Look up the corresponding translation key in help groups
                    for _, cmds in _help_groups():
                        for cmd_text, translated_desc in cmds:
                            if cmd_text.split()[0].replace("-", "_") == cmd_name:
                                print(f"{prefix} — {translated_desc}")
                                return
                    # 未找到匹配（如 print-example），直接输出
                    # [EN] No match found (e.g. print-example), output directly
                    print(doc)
                else:
                    print(doc)
            else:
                print(tr("icli_unknown_cmd", "未知命令：{}").format(arg))
            return

        print()
        print(_bold(tr("icli_help_header", "🌊 WW3Tool 交互式命令行")))
        print(_color(tr("icli_help_hint", "输入命令后按回车执行，Tab 键自动补全，↑↓ 翻阅历史"), _Colors.CYAN))
        print()

        groups = _help_groups()

        # 计算命令列最大宽度
        # [EN] Calculate maximum width for the command column
        max_cmd_len = max(
            len(cmd_text)
            for _, cmds in groups
            for cmd_text, _ in cmds
        )

        for group_name, commands in groups:
            print(f"  {_bold(_color(group_name, _Colors.YELLOW))}")
            for cmd_text, desc in commands:
                padding = " " * (max_cmd_len - len(cmd_text) + 2)
                print(f"    {_color(cmd_text, _Colors.GREEN)}{padding}{desc}")
            print()

        print(f"  {_bold(_color(tr('icli_global_options', '全局选项'), _Colors.YELLOW))}")
        print(f"    {_color('--lang <zh_CN|en_US>', _Colors.GREEN)}      {tr('icli_lang_desc', '切换输出语言')}")
        print()

        # 典型流程提示（上下分叉：本地 vs 远程）
        # [EN] Typical workflow hint (fork: local vs remote)
        g = _color
        print(f"  {_bold(_color(tr('icli_workflow', '典型流程'), _Colors.YELLOW))}")
        print(f"    {g('create-workdir', _Colors.GREEN)} → {g('prepare-forcing', _Colors.GREEN)} → {g('generate-grid', _Colors.GREEN)} → {g('run-pre-workflow', _Colors.GREEN)} → {g('plot-wave-maps', _Colors.GREEN)}")
        print(f"                                                                                         └→ {g('upload', _Colors.GREEN)} → {g('submit', _Colors.GREEN)} → {g('check-status', _Colors.GREEN)} → {g('download-results', _Colors.GREEN)}")
        print()

    def parseline(self, line: str) -> tuple[str | None, str | None, str]:
        """重写行解析：支持含 '-' 的命令名（如 prepare-forcing → do_prepare_forcing）。

        [EN] Override line parsing: support command names containing '-' (e.g. prepare-forcing -> do_prepare_forcing).
        """
        stripped = line.strip()
        if not stripped:
            return None, None, line
        # 提取第一个 token（命令名），将其中的 '-' 替换为 '_'
        # [EN] Extract the first token (command name), replacing '-' with '_'
        parts = stripped.split(None, 1)
        cmd_name = parts[0].replace("-", "_")
        arg = parts[1] if len(parts) > 1 else ""
        # 检查是否对应已注册的 do_xxx 方法
        # [EN] Check if it corresponds to a registered do_xxx method
        if hasattr(self, f"do_{cmd_name}"):
            return cmd_name, arg, line
        # 回退到默认解析（处理 help、? 等内置命令）
        # [EN] Fall back to default parsing (handle built-in commands like help, ?)
        return super().parseline(line)

    def _load_config(self, path: str) -> bool:
        """加载或重新加载 params.yml 配置文件。

        [EN] Load or reload a params.yml configuration file.
        """
        try:
            # 去除用户可能输入的引号
            # [EN] Strip any quotes the user may have entered
            path = path.strip().strip("'\"")
            source = Path(path).expanduser().resolve()
            self._config = load_pipeline_config(str(source), validation_stage="plot")
            self._params_path = source
            print(_success(tr("icli_loaded_config", "✓ 已加载配置：{}").format(source)))
            return True
        except ConfigError as exc:
            print(_error(tr("icli_config_error", "✗ 配置错误：{}").format(exc)))
            return False
        except Exception as exc:
            print(_error(tr("icli_load_failed", "✗ 加载失败：{}").format(exc)))
            return False

    def _require_config(self) -> bool:
        """检查是否已加载配置，未加载时提示用户。

        [EN] Check if a configuration has been loaded; prompt the user if not.
        """
        if self._config is None:
            print(_warn(tr("icli_no_config", "⚠ 未加载配置文件，请先使用 'load <params.yml>' 加载参数")))
            return False
        return True

    def _log_callback(self, message: str) -> None:
        """日志回调函数，实时输出到终端。

        [EN] Log callback function, outputs in real time to the terminal.
        """
        print(message)

    # ── 配置管理命令 ─────────────────────────────────────────────────────
    # [EN] ── Configuration management commands ───────────────────────────

    def do_load(self, arg: str) -> None:
        """load <params.yml>  — 加载参数配置文件

        [EN] load <params.yml>  — Load a parameter configuration file
        """
        if not arg.strip():
            print(_warn(tr("icli_usage_load", "用法：load <params.yml 路径>")))
            return
        self._load_config(arg.strip())

    def do_config(self, arg: str) -> None:
        """config  — 显示当前配置摘要

        [EN] config  — Display current configuration summary
        """
        if not self._require_config():
            return
        cfg = self._config
        not_set = tr("icli_not_set", "(未设置)")
        not_cfg = tr("icli_not_configured", "(未配置)")

        print(_bold("\n" + tr("icli_config_summary", "📋 当前配置摘要")))
        print(f"  {tr('icli_config_file', '配置文件：{}').format(self._params_path)}")
        print(f"  {tr('icli_workdir', '工作目录：{}').format(cfg.workdir.path)}")

        # 网格
        print(f"\n  {_bold(tr('icli_config_grid', '网格'))}")
        print(f"    {tr('icli_grid_type', '类型：{} / {}').format(cfg.grid.mesh_type, cfg.grid.grid_type)}")
        outer = cfg.grid.outer
        if outer and outer.lon and outer.lat:
            print(f"    {tr('icli_grid_range', '范围：经度 {} ~ {}，纬度 {} ~ {}').format(outer.lon[0], outer.lon[1], outer.lat[0], outer.lat[1])}")
        if cfg.grid.mesh_type == "structured" and cfg.grid.structured:
            s = cfg.grid.structured
            if outer and outer.dx and outer.dy:
                print(f"    dx={outer.dx}, dy={outer.dy}")
            print(f"    {tr('icli_bathymetry', '水深：{}').format(s.bathymetry or not_set)}")
            print(f"    {tr('icli_coastline', '海岸线：{}').format(s.coastline_precision or not_set)}")
        elif cfg.grid.mesh_type == "smc" and cfg.grid.smc:
            s = cfg.grid.smc
            print(f"    {tr('icli_bathymetry', '水深：{}').format(s.bathymetry or not_set)}")
            print(f"    {tr('icli_smc_levels', '层数：{}').format(s.n_levels or not_set)}")
        elif cfg.grid.mesh_type == "unstructured" and cfg.grid.unstructured:
            u = cfg.grid.unstructured
            print(f"    {tr('icli_unst_hmax', 'hmax：{}').format(u.hmax or not_set)}")

        # 强迫场
        print(f"\n  {_bold(tr('icli_forcing', '强迫场'))}")
        print(f"    {tr('icli_wind', '风场：{}').format(cfg.forcing.wind or not_set)}")
        print(f"    {tr('icli_current', '流场：{}').format(cfg.forcing.current or not_set)}")
        print(f"    {tr('icli_level', '水位：{}').format(cfg.forcing.level or not_set)}")
        print(f"    {tr('icli_ice', '海冰：{}').format(cfg.forcing.ice or not_set)}")
        print(f"    {tr('icli_process_mode', '处理模式：{}').format(cfg.forcing.process_mode)}")
        print(f"    {tr('icli_auto_associate', '自动关联：{}').format('✓' if cfg.forcing.auto_associate else '✗')}")

        # 计算模式
        print(f"\n  {_bold(tr('icli_config_calc', '计算模式'))}")
        print(f"    {tr('icli_calc_mode', '模式：{}').format(cfg.calc.mode or not_set)}")
        if cfg.calc.mode == "point":
            print(f"    {tr('icli_spectral_points', '谱点数：{}').format(len(cfg.calc.points))}")
        elif cfg.calc.mode == "track":
            print(f"    {tr('icli_track_points', '航迹点数：{}').format(len(cfg.calc.track_points))}")

        # WW3 配置
        print(f"\n  {_bold(tr('icli_config_ww3', 'WW3 配置'))}")
        print(f"    {tr('icli_ww3_period', '时段：{} ~ {}').format(cfg.ww3.start_date, cfg.ww3.end_date)}")
        print(f"    {tr('icli_compute_precision', '计算精度：{}s').format(cfg.ww3.compute_precision or not_set)}")
        print(f"    {tr('icli_output_precision', '输出精度：{}s').format(cfg.ww3.output_precision or not_set)}")
        print(f"    {tr('icli_output_scheme', '输出方案：{}').format(cfg.ww3.output_scheme or not_set)}")
        print(f"    {tr('icli_ww3_st', 'ST：{}').format(cfg.ww3.st or not_cfg)}")

        # WW3 Grid 参数
        wg = cfg.ww3_grid.parameters if cfg.ww3_grid and cfg.ww3_grid.parameters else {}
        if wg:
            spectrum = f"XFR={wg.get('SPECTRUM%XFR', '?')}, FREQ1={wg.get('SPECTRUM%FREQ1', '?')}, NK={wg.get('SPECTRUM%NK', '?')}, NTH={wg.get('SPECTRUM%NTH', '?')}"
            timesteps = f"DTMAX={wg.get('TIMESTEPS%DTMAX', '?')}, DTXY={wg.get('TIMESTEPS%DTXY', '?')}, DTKTH={wg.get('TIMESTEPS%DTKTH', '?')}, DTMIN={wg.get('TIMESTEPS%DTMIN', '?')}"
            print(f"    {tr('icli_spectrum_params', '频谱：{}').format(spectrum)}")
            print(f"    {tr('icli_timesteps_params', '时间步：{}').format(timesteps)}")

        # Slurm
        print(f"\n  {_bold(tr('icli_config_slurm', 'Slurm'))}")
        print(f"    {tr('icli_slurm_cpu', 'CPU：{}').format(cfg.slurm.cpu or not_cfg)}")
        print(f"    {tr('icli_slurm_cores', '核数：{}').format(cfg.slurm.cores)}")
        print(f"    {tr('icli_slurm_nodes', '节点：{}').format(cfg.slurm.nodes)}")
        if cfg.slurm.cpu_group:
            print(f"    {tr('icli_slurm_cpu_group', 'CPU 组：{}').format(cfg.slurm.cpu_group)}")

        # 服务器
        print(f"\n  {_bold(tr('icli_config_server', '服务器'))}")
        print(f"    {tr('icli_server', '主机：{}').format(cfg.server.host or not_cfg)}")
        if cfg.server.host:
            print(f"    {tr('icli_server_user', '用户：{}').format(cfg.server.user or not_cfg)}")
            print(f"    {tr('icli_remote_dir', '远程目录：{}').format(cfg.server.default_remote_dir or not_cfg)}")

        # 绘图
        print(f"\n  {_bold(tr('icli_config_plot', '绘图'))}")
        wm = cfg.plot.wave_maps
        print(f"    {tr('icli_plot_wave_maps', '波高图：{}').format('✓' if wm.enabled else '✗')}")
        if wm.enabled:
            if wm.time_step_hours is not None:
                print(f"    {tr('icli_plot_time_step', '时间步长：{}h').format(wm.time_step_hours)}")
            if wm.generate_video:
                print(f"    {tr('icli_plot_video', '生成视频：✓')}")
            if wm.dpi is not None:
                print(f"    DPI：{wm.dpi}")
            if wm.figsize:
                print(f"    {tr('icli_plot_figsize', '图片尺寸：{}').format(wm.figsize)}")
        sp = cfg.plot.spectrum
        print(f"    {tr('icli_plot_spectrum', '二维谱：{}').format('✓' if sp.enabled else '✗')}")
        if sp.enabled:
            if sp.time_step_hours is not None:
                print(f"    {tr('icli_plot_time_step', '时间步长：{}h').format(sp.time_step_hours)}")
            if sp.energy_threshold is not None:
                print(f"    {tr('icli_plot_energy_threshold', '能量阈值：{}').format(sp.energy_threshold)}")
            if sp.plot_mode:
                print(f"    {tr('icli_plot_plot_mode', '绘制方式：{}').format(sp.plot_mode)}")
        j3 = cfg.plot.jason3
        print(f"    {tr('icli_plot_jason3', 'Jason-3：{}').format('✓' if j3.enabled else '✗')}")
        if j3.enabled:
            if j3.data_folder:
                print(f"    {tr('icli_plot_data_folder', '数据目录：{}').format(j3.data_folder)}")
            if j3.time_range:
                print(f"    {tr('icli_plot_time_range', '时间范围：{}').format(' ~ '.join(j3.time_range))}")
            if j3.max_dist_deg is not None:
                print(f"    {tr('icli_plot_max_dist', '最大距离：{}°').format(j3.max_dist_deg)}")
            if j3.time_window_hours is not None:
                print(f"    {tr('icli_plot_time_window', '时间窗口：{}h').format(j3.time_window_hours)}")
        nb = cfg.plot.ndbc
        print(f"    {tr('icli_plot_ndbc', 'NDBC：{}').format('✓' if nb.enabled else '✗')}")
        if nb.enabled:
            if nb.data_folder:
                print(f"    {tr('icli_plot_data_folder', '数据目录：{}').format(nb.data_folder)}")
            if nb.time_range:
                print(f"    {tr('icli_plot_time_range', '时间范围：{}').format(' ~ '.join(nb.time_range))}")
            if nb.download:
                print(f"    {tr('icli_plot_download', '自动下载：✓')}")
        wf = cfg.plot.wind_field
        if wf.time_step_hours is not None:
            print(f"    {tr('icli_plot_wind_field', '风场：✓')}")
            print(f"    {tr('icli_plot_time_step', '时间步长：{}h').format(wf.time_step_hours)}")
            if wf.flag_type:
                print(f"    {tr('icli_plot_flag_type', '风向标志：{}').format(wf.flag_type)}")
            if wf.flag_density is not None:
                print(f"    {tr('icli_plot_flag_density', '标志密度：{}').format(wf.flag_density)}")
        elif wf.flag_type or wf.flag_density is not None:
            print(f"    {tr('icli_plot_wind_field', '风场：✓')}")
            if wf.flag_type:
                print(f"    {tr('icli_plot_flag_type', '风向标志：{}').format(wf.flag_type)}")
            if wf.flag_density is not None:
                print(f"    {tr('icli_plot_flag_density', '标志密度：{}').format(wf.flag_density)}")
        print()

    def do_print(self, arg: str) -> None:
        """print  — 输出当前 params.yml 内容

        [EN] print  — Output current params.yml content
        """
        if not self._require_config():
            return
        try:
            content = self._params_path.read_text(encoding="utf-8")
            print(content)
        except Exception as exc:
            print(_error(tr("icli_exec_failed", "✗ 执行失败：{}").format(exc)))

    def do_create_workdir(self, arg: str) -> None:
        """create-workdir <name>  — 从模板创建新工作目录

        [EN] create-workdir <name>  — Create a new working directory from template
        """
        name = arg.strip().strip("'\"")
        if not name:
            print(_warn(tr("icli_usage_create_workdir", "用法：create-workdir <目录名称>")))
            return

        # 查找根 params.yml 模板
        # [EN] Look for the root params.yml template
        root = Path(__file__).resolve().parents[3]
        root_params = root / "params.yml"
        if not root_params.is_file():
            print(_error(tr("icli_no_template", "✗ 仓库根目录没有 params.yml 模板文件")))
            return

        workdir = Path.cwd() / name
        if workdir.exists():
            print(_error(tr("icli_dir_exists", "✗ 目录已存在：{}").format(workdir)))
            return

        workdir.mkdir(parents=True)
        target = workdir / "params.yml"
        shutil.copy2(str(root_params), str(target))

        # 自动将 workdir.path 改为新目录路径
        # [EN] Automatically update workdir.path to the new directory path
        import re
        content = target.read_text(encoding="utf-8")
        content = re.sub(
            r"(^workdir:\s*\n  path:\s*).*",
            rf"\g<1>{workdir}",
            content,
            count=1,
            flags=re.MULTILINE,
        )
        target.write_text(content, encoding="utf-8")

        print(_success(tr("icli_created_workdir", "✓ 已创建工作目录：{}").format(workdir)))
        print(tr("icli_edit_or_load", "  请编辑 {} 或 load 其他 params.yml").format(target))

    def complete_create_workdir(self, text: str, line: str, begidx: int, endidx: int) -> list[str]:
        return []

    # ── 预处理命令 ─────────────────────────────────────────────────────────
    # [EN] ── Preprocessing commands ───────────────────────────────────────

    def do_validate(self, arg: str) -> None:
        """validate [--stage forcing|grid|full]  — 校验当前配置文件

        [EN] validate [--stage forcing|grid|full]  — Validate current configuration file
        """
        if not self._require_config():
            return
        stage = "full"
        parts = arg.split()
        for i, part in enumerate(parts):
            if part == "--stage" and i + 1 < len(parts):
                stage = parts[i + 1]
        try:
            load_pipeline_config(str(self._params_path), validation_stage=stage)
            print(_success(tr("icli_validated", "✓ 配置文件校验通过（{}）").format(stage)))
        except ConfigError as exc:
            print(_error(tr("icli_validate_failed", "✗ 校验失败：{}").format(exc)))

    def complete_validate(self, text: str, line: str, begidx: int, endidx: int) -> list[str]:
        return self._complete_options(text, ["--stage", "--stage forcing", "--stage grid", "--stage full"])

    def do_prepare_forcing(self, arg: str) -> None:
        """prepare-forcing  — 准备强迫场（Step 1）

        [EN] prepare-forcing  — Prepare forcing fields (Step 1)
        """
        if not self._require_config():
            return
        try:
            from ..application.preprocessing_workflow import run_prepare_forcing
            print(_info(tr("icli_start_forcing", "▶ 开始准备强迫场...")))
            run_prepare_forcing(self._config, log=self._log_callback)
            print(_success(tr("icli_done_forcing", "✓ 强迫场准备完成")))
        except Exception as exc:
            print(_error(tr("icli_exec_failed", "✗ 执行失败：{}").format(exc)))

    def do_generate_grid(self, arg: str) -> None:
        """generate-grid [--no-cache]  — 生成网格（Step 2）

        [EN] generate-grid [--no-cache]  — Generate grid (Step 2)
        """
        if not self._require_config():
            return
        use_cache = "--no-cache" not in arg
        try:
            from ..application.grid_preparation import run_generate_grid
            print(_info(tr("icli_start_grid", "▶ 开始生成网格...")))
            run_generate_grid(self._config, log=self._log_callback, use_cache=use_cache)
            print(_success(tr("icli_done_grid", "✓ 网格生成完成")))
        except Exception as exc:
            print(_error(tr("icli_exec_failed", "✗ 执行失败：{}").format(exc)))

    def do_run_pre_workflow(self, arg: str) -> None:
        """run-pre-workflow [--skip-grid] [--no-cache]  — 完整预处理流程

        [EN] run-pre-workflow [--skip-grid] [--no-cache]  — Full preprocessing pipeline
        """
        if not self._require_config():
            return
        skip_grid = "--skip-grid" in arg
        use_cache = "--no-cache" not in arg
        try:
            from ..application.preprocessing_workflow import run_pipeline
            print(_info(tr("icli_start_pipeline", "▶ 开始完整预处理...")))
            run_pipeline(
                self._config,
                log=self._log_callback,
                skip_grid=skip_grid,
                use_grid_cache=use_cache,
            )
            print(_success(tr("icli_done_pipeline", "✓ 预处理完成")))
        except Exception as exc:
            print(_error(tr("icli_exec_failed", "✗ 执行失败：{}").format(exc)))

    def do_prepare_ww3(self, arg: str) -> None:
        """prepare-ww3  — 仅生成 WW3 namelist（不重跑强迫场和网格）

        [EN] prepare-ww3  — Generate WW3 namelist only (without re-running forcing and grid)
        """
        if not self._require_config():
            return
        try:
            from ..infrastructure.forcing.use_cases import ScanWorkdirForcingUseCase
            from ..infrastructure.forcing.file_service import FileService
            from ..infrastructure.adapters.ww3_namelist_adapter import prepare_ww3_files
            from ..support.logging import CoreLogger

            logger = CoreLogger(callback=self._log_callback)
            file_service = FileService(logger=logger)
            files = ScanWorkdirForcingUseCase(file_service).execute(str(self._config.workdir.path))
            print(_info(tr("icli_start_prepare_ww3", "▶ 正在生成 WW3 namelist...")))
            prepare_ww3_files(self._config, files, logger)
            print(_success(tr("icli_done_prepare_ww3", "✓ WW3 namelist 生成完成")))
        except Exception as exc:
            print(_error(tr("icli_exec_failed", "✗ 执行失败：{}").format(exc)))

    def do_plot_wave_maps(self, arg: str) -> None:
        """plot-wave-maps [--contour]  — 生成波高填色图或等值线图

        [EN] plot-wave-maps [--contour]  — Generate wave height filled-color or contour maps
        """
        if not self._require_config():
            return
        contour = "--contour" in arg
        try:
            from .command_line import _run_wave_maps
            print(_info(tr("icli_start_wave_maps", "▶ 开始生成波高图...")))
            rc = _run_wave_maps(self._config, contour=contour)
            if rc == 0:
                print(_success(tr("icli_done_wave_maps", "✓ 波高图生成完成")))
            else:
                print(_error(tr("icli_failed_wave_maps", "✗ 波高图生成失败")))
        except Exception as exc:
            print(_error(tr("icli_exec_failed", "✗ 执行失败：{}").format(exc)))

    def do_plot_spectrum(self, arg: str) -> None:
        """plot-spectrum [--mode first|all|selected] [--station N]  — 生成方向谱图

        [EN] plot-spectrum [--mode first|all|selected] [--station N]  — Generate directional spectrum plots
        """
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
            print(_info(tr("icli_start_spectrum", "▶ 开始生成方向谱图...")))
            rc = _run_spectrum(self._config, mode=mode, station_index=station)
            if rc == 0:
                print(_success(tr("icli_done_spectrum", "✓ 方向谱图生成完成")))
            else:
                print(_error(tr("icli_failed_spectrum", "✗ 方向谱图生成失败")))
        except Exception as exc:
            print(_error(tr("icli_exec_failed", "✗ 执行失败：{}").format(exc)))

    def do_plot_jason3(self, arg: str) -> None:
        """plot-jason3  — WW3 结果与 Jason-3 卫星数据匹配

        [EN] plot-jason3  — Match WW3 output with Jason-3 satellite data
        """
        if not self._require_config():
            return
        try:
            from .command_line import _run_match_jason3
            print(_info(tr("icli_start_jason3", "▶ 开始 Jason-3 匹配...")))
            rc = _run_match_jason3(self._config)
            if rc == 0:
                print(_success(tr("icli_done_jason3", "✓ Jason-3 匹配完成")))
            else:
                print(_error(tr("icli_failed_jason3", "✗ Jason-3 匹配失败")))
        except Exception as exc:
            print(_error(tr("icli_exec_failed", "✗ 执行失败：{}").format(exc)))

    def do_plot_jason3_swh(self, arg: str) -> None:
        """plot-jason3-swh  — 绘制 Jason-3 卫星 SWH / 轨迹图

        [EN] plot-jason3-swh  — Plot Jason-3 satellite SWH / track maps
        """
        if not self._require_config():
            return
        try:
            from .command_line import _run_jason3_swh
            print(_info(tr("icli_start_jason3_swh", "▶ 开始生成 Jason-3 卫星观测图...")))
            rc = _run_jason3_swh(self._config)
            if rc == 0:
                print(_success(tr("icli_done_jason3_swh", "✓ Jason-3 卫星观测图生成完成")))
            else:
                print(_error(tr("icli_failed_jason3_swh", "✗ Jason-3 卫星观测图生成失败")))
        except Exception as exc:
            print(_error(tr("icli_exec_failed", "✗ 执行失败：{}").format(exc)))

    def do_download_jason3(self, arg: str) -> None:
        """download-jason3  — 下载 Jason-3 L2 数据

        [EN] download-jason3  — Download Jason-3 L2 data
        """
        if not self._require_config():
            return
        try:
            from .command_line import _run_download_jason3
            print(_info(tr("icli_start_download_jason3", "▶ 开始下载 Jason-3 数据...")))
            rc = _run_download_jason3(self._config)
            if rc == 0:
                print(_success(tr("icli_done_download_jason3", "✓ Jason-3 数据下载完成")))
            else:
                print(_error(tr("icli_failed_download_jason3", "✗ Jason-3 数据下载失败")))
        except Exception as exc:
            print(_error(tr("icli_exec_failed", "✗ 执行失败：{}").format(exc)))

    def do_plot_ndbc(self, arg: str) -> None:
        """plot-ndbc [--download]  — WW3 结果与 NDBC 浮标匹配或下载数据

        [EN] plot-ndbc [--download]  — Match WW3 output with NDBC buoys or download data
        """
        if not self._require_config():
            return
        download = "--download" in arg
        try:
            from .command_line import _run_match_ndbc
            print(_info(tr("icli_start_ndbc", "▶ 开始 NDBC 处理...")))
            rc = _run_match_ndbc(self._config, download=download)
            if rc == 0:
                print(_success(tr("icli_done_ndbc", "✓ NDBC 处理完成")))
            else:
                print(_error(tr("icli_failed_ndbc", "✗ NDBC 处理失败")))
        except Exception as exc:
            print(_error(tr("icli_exec_failed", "✗ 执行失败：{}").format(exc)))

    # ── 远程运维命令 ───────────────────────────────────────────────────────
    # [EN] ── Remote operations commands ────────────────────────────────────

    def do_connect_test(self, arg: str) -> None:
        """connect-test  — 测试 SSH 连接

        [EN] connect-test  — Test SSH connection
        """
        if not self._require_config():
            return
        try:
            from ..application.remote_ops import run_connect_test
            print(_info(tr("icli_start_connect", "▶ 测试连接...")))
            result = run_connect_test(self._config, log=self._log_callback)
            if result.success:
                print(_success(tr("icli_done_connect", "✓ 连接成功")))
            else:
                print(_error(tr("icli_failed_connect", "✗ 连接失败：{}").format(result.error)))
        except Exception as exc:
            print(_error(tr("icli_exec_failed", "✗ 执行失败：{}").format(exc)))

    def do_ssh(self, arg: str) -> None:
        """ssh  — 打开交互式 SSH 终端

        [EN] ssh  — Open an interactive SSH terminal
        """
        if not self._require_config():
            return
        server = self._config.server
        if not server.host or not server.user:
            print(_warn(tr("icli_ssh_not_configured", "⚠ 请先在 params.yml server: 中配置 host 和 user")))
            return

        # 优先使用系统 ssh 命令（完整交互体验）
        # [EN] Prefer system ssh command (full interactive experience)
        ssh_cmd = ["ssh", "-p", str(server.port)]
        if server.key_file:
            ssh_cmd.extend(["-i", str(server.key_file)])
        ssh_cmd.append(f"{server.user}@{server.host}")

        print(_info(tr("icli_opening_ssh", "▶ 正在打开 SSH 终端：{}").format(f"{server.user}@{server.host}:{server.port}")))
        print(_info(tr("icli_ssh_hint", "  提示：输入 exit 或按 Ctrl+D 关闭 SSH 终端并返回 ww3>")))
        print()

        try:
            # 使用系统 ssh 客户端（支持完整交互）
            # [EN] Use system ssh client (supports full interaction)
            ret = subprocess.call(ssh_cmd)
            if ret != 0:
                print()
                print(_warn(tr("icli_ssh_returned", "⚠ SSH 会话已结束，返回码：{}").format(ret)))
                # 如果系统 ssh 失败且配置了密码，尝试 paramiko 回退
                # [EN] If system ssh fails and password is configured, try paramiko fallback
                if server.password and ret != 0:
                    print(_info(tr("icli_ssh_paramiko_fallback", "  尝试使用 paramiko 回退连接...")))
                    self._ssh_via_paramiko()
        except FileNotFoundError:
            # 系统 ssh 命令不存在，回退到 paramiko
            # [EN] System ssh command not found, fall back to paramiko
            print(_warn(tr("icli_no_ssh_binary", "⚠ 未找到系统 ssh 命令，使用 paramiko 回退")))
            self._ssh_via_paramiko()
        except KeyboardInterrupt:
            print()
            print(_info(tr("icli_ssh_interrupted", "  SSH 会话已中断")))

    def _ssh_via_paramiko(self) -> None:
        """使用 paramiko invoke_shell 提供交互式 SSH 终端（回退方案）。

        [EN] Provide an interactive SSH terminal using paramiko invoke_shell (fallback).
        """
        try:
            from ..infrastructure.remote.ssh_client import SshClient
        except ImportError:
            print(_error(tr("icli_need_paramiko", "✗ 需要 paramiko 才能使用 SSH 功能")))
            return

        server = self._config.server
        client = SshClient(server)
        try:
            client.connect(log=self._log_callback)
            print(_success(tr("icli_ssh_connected", "✓ 已连接，SSH 终端已打开")))
            print(_info(tr("icli_ssh_exit_hint", "  输入 exit 或按 Ctrl+D 关闭终端")))
            print()

            # 获取 paramiko SSH client 并打开交互式 shell
            # [EN] Get the paramiko SSH client and open an interactive shell
            ssh = client._ssh
            channel = ssh.invoke_shell()
            channel.settimeout(0.1)

            import select
            while True:
                # 检查是否有数据可读
                # [EN] Check if there is data available to read
                r, _, _ = select.select([channel, sys.stdin], [], [], 0.1)
                if channel in r:
                    try:
                        data = channel.recv(4096)
                        if not data:
                            break
                        sys.stdout.write(data.decode("utf-8", errors="replace"))
                        sys.stdout.flush()
                    except Exception:
                        break
                if sys.stdin in r:
                    try:
                        line = sys.stdin.readline()
                        if not line:
                            break
                        channel.send(line.encode("utf-8"))
                    except Exception:
                        break
        except Exception as exc:
            print(_error(tr("icli_ssh_failed", "✗ SSH 连接失败：{}").format(exc)))
        finally:
            client.close()
            print()
            print(_info(tr("icli_ssh_closed", "  SSH 终端已关闭")))

    def do_list_files(self, arg: str) -> None:
        """list-files  — 列出远程工作目录文件

        [EN] list-files  — List files in the remote working directory
        """
        if not self._require_config():
            return
        try:
            from ..application.remote_ops import run_list_files
            print(_info(tr("icli_start_list_files", "▶ 获取文件列表...")))
            result = run_list_files(self._config, log=self._log_callback)
            if not result.success:
                print(_error(tr("icli_failed_list_files", "✗ 获取失败：{}").format(result.error)))
        except Exception as exc:
            print(_error(tr("icli_exec_failed", "✗ 执行失败：{}").format(exc)))

    def do_upload(self, arg: str) -> None:
        """upload --confirm  — 上传本地工作目录到远程（需 --confirm）

        [EN] upload --confirm  — Upload local working directory to remote (requires --confirm)
        """
        if not self._require_config():
            return
        if "--confirm" not in arg:
            print(_warn(tr("icli_upload_dangerous", "⚠ upload 是破坏性操作，必须加 --confirm 才能执行")))
            print(_warn(tr("icli_usage_upload", "  用法：upload --confirm")))
            return
        try:
            from ..application.remote_ops import run_upload
            print(_info(tr("icli_start_upload", "▶ 开始上传...")))
            result = run_upload(self._config, log=self._log_callback, confirmed=True)
            if result.success:
                print(_success(tr("icli_done_upload", "✓ 上传完成")))
            else:
                print(_error(tr("icli_failed_upload", "✗ 上传失败：{}").format(result.error)))
        except Exception as exc:
            print(_error(tr("icli_exec_failed", "✗ 执行失败：{}").format(exc)))

    def do_submit(self, arg: str) -> None:
        """submit [--script server.sh]  — 在远程执行提交脚本

        [EN] submit [--script server.sh]  — Execute a submit script on the remote server
        """
        if not self._require_config():
            return
        script = "server.sh"
        parts = arg.split()
        for i, part in enumerate(parts):
            if part == "--script" and i + 1 < len(parts):
                script = parts[i + 1]
        try:
            from ..application.remote_ops import run_submit
            print(_info(tr("icli_start_submit", "▶ 执行远程脚本：{}...").format(script)))
            result = run_submit(self._config, log=self._log_callback, script=script)
            if result.success:
                print(_success(tr("icli_done_submit", "✓ 脚本执行完成")))
            else:
                print(_error(tr("icli_failed_submit", "✗ 脚本执行失败：{}").format(result.error)))
        except Exception as exc:
            print(_error(tr("icli_exec_failed", "✗ 执行失败：{}").format(exc)))

    def do_check_status(self, arg: str) -> None:
        """check-status  — 检查远程任务状态

        [EN] check-status  — Check remote task status
        """
        if not self._require_config():
            return
        try:
            from ..application.remote_ops import run_check_status
            print(_info(tr("icli_start_check", "▶ 检查状态...")))
            result = run_check_status(self._config, log=self._log_callback)
            if not result.success:
                print(_error(tr("icli_failed_check", "✗ 检查失败：{}").format(result.error)))
        except Exception as exc:
            print(_error(tr("icli_exec_failed", "✗ 执行失败：{}").format(exc)))

    def do_queue_status(self, arg: str) -> None:
        """queue-status  — 查看 SLURM 队列

        [EN] queue-status  — View SLURM queue
        """
        if not self._require_config():
            return
        try:
            from ..application.remote_ops import run_queue_status
            print(_info(tr("icli_start_queue", "▶ 获取队列状态...")))
            result = run_queue_status(self._config, log=self._log_callback)
            if not result.success:
                print(_error(tr("icli_failed_queue", "✗ 获取失败：{}").format(result.error)))
        except Exception as exc:
            print(_error(tr("icli_exec_failed", "✗ 执行失败：{}").format(exc)))

    def do_download_results(self, arg: str) -> None:
        """download-results [--nested]  — 下载远程 WW3 结果

        [EN] download-results [--nested]  — Download remote WW3 results
        """
        if not self._require_config():
            return
        nested = "--nested" in arg
        try:
            from ..application.remote_ops import run_download_results
            print(_info(tr("icli_start_download_results", "▶ 下载结果文件...")))
            result = run_download_results(self._config, log=self._log_callback, nested=nested)
            if result.success:
                print(_success(tr("icli_done_download_results", "✓ 下载完成")))
            else:
                print(_error(tr("icli_failed_download_results", "✗ 下载失败：{}").format(result.error)))
        except Exception as exc:
            print(_error(tr("icli_exec_failed", "✗ 执行失败：{}").format(exc)))

    def do_download_log(self, arg: str) -> None:
        """download-log  — 下载远程日志文件

        [EN] download-log  — Download remote log files
        """
        if not self._require_config():
            return
        try:
            from ..application.remote_ops import run_download_log
            print(_info(tr("icli_start_download_log", "▶ 下载日志...")))
            result = run_download_log(self._config, log=self._log_callback)
            if result.success:
                print(_success(tr("icli_done_download_log", "✓ 日志下载完成")))
            else:
                print(_error(tr("icli_failed_download_log", "✗ 日志下载失败：{}").format(result.error)))
        except Exception as exc:
            print(_error(tr("icli_exec_failed", "✗ 执行失败：{}").format(exc)))

    def do_clear_remote(self, arg: str) -> None:
        """clear-remote --confirm  — 清空远程工作目录（需 --confirm）

        [EN] clear-remote --confirm  — Clear remote working directory (requires --confirm)
        """
        if not self._require_config():
            return
        if "--confirm" not in arg:
            print(_warn(tr("icli_clear_dangerous", "⚠ clear-remote 是破坏性操作，必须加 --confirm 才能执行")))
            print(_warn(tr("icli_usage_clear", "  用法：clear-remote --confirm")))
            return
        try:
            from ..application.remote_ops import run_clear_remote
            print(_info(tr("icli_start_clear", "▶ 清空远程目录...")))
            result = run_clear_remote(self._config, log=self._log_callback, confirmed=True)
            if result.success:
                print(_success(tr("icli_done_clear", "✓ 远程目录已清空")))
            else:
                print(_error(tr("icli_failed_clear", "✗ 清空失败：{}").format(result.error)))
        except Exception as exc:
            print(_error(tr("icli_exec_failed", "✗ 执行失败：{}").format(exc)))

    def do_cancel_job(self, arg: str) -> None:
        """cancel-job <job_id>  — 取消 SLURM 任务

        [EN] cancel-job <job_id>  — Cancel a SLURM job
        """
        if not self._require_config():
            return
        job_id = arg.strip()
        if not job_id:
            print(_warn(tr("icli_usage_cancel", "用法：cancel-job <job_id>")))
            return
        try:
            from ..application.remote_ops import run_cancel_job
            print(_info(tr("icli_start_cancel", "▶ 取消任务 {}...").format(job_id)))
            result = run_cancel_job(self._config, job_id, log=self._log_callback)
            if result.success:
                print(_success(tr("icli_done_cancel", "✓ 任务已取消")))
            else:
                print(_error(tr("icli_failed_cancel", "✗ 取消失败：{}").format(result.error)))
        except Exception as exc:
            print(_error(tr("icli_exec_failed", "✗ 执行失败：{}").format(exc)))

    # ── 辅助命令 ───────────────────────────────────────────────────────────
    # [EN] ── Auxiliary commands ────────────────────────────────────────────

    def do_print_example(self, arg: str) -> None:
        """print-example  — 打印示例 params.yml

        [EN] print-example  — Print example params.yml
        """
        print(EXAMPLE_YAML)

    def do_exit(self, arg: str) -> bool:
        """exit  — 退出交互式 CLI

        [EN] exit  — Exit the interactive CLI
        """
        print(_info(tr("icli_goodbye", "👋 再见！")))
        return True

    def do_quit(self, arg: str) -> bool:
        """quit  — 退出交互式 CLI

        [EN] quit  — Exit the interactive CLI
        """
        return self.do_exit(arg)

    def do_EOF(self, arg: str) -> bool:
        """处理 Ctrl+D

        [EN] Handle Ctrl+D
        """
        print()
        return self.do_exit(arg)

    # ── 自动补全支持 ───────────────────────────────────────────────────────
    # [EN] ── Auto-completion support ───────────────────────────────────────

    def complete_load(self, text: str, line: str, begidx: int, endidx: int) -> list[str]:
        """Tab 补全文件路径

        [EN] Tab-complete file paths
        """
        if not text:
            return [str(p) for p in Path(".").glob("*.yml")]
        return [str(p) for p in Path(text).parent.glob(f"{Path(text).name}*.yml")]

    # 为所有命令添加通用补全（参数选项）
    # [EN] Add generic completion for all commands (argument options)
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


def _find_default_params() -> Optional[str]:
    """查找项目根目录下的 params.yml，返回其路径或 None。

    [EN] Look for params.yml under the project root directory; return its path or None.
    """
    # interactive_cli.py 位于 src/workflows/interfaces/
    # [EN] interactive_cli.py is located at src/workflows/interfaces/
    root = Path(__file__).resolve().parents[3]
    default = root / "params.yml"
    if default.is_file():
        return str(default)
    return None


def main(params_path: Optional[str] = None) -> int:
    """交互式 CLI 主入口。

    Args:
        params_path: 可选，启动时自动加载的 params.yml 路径。
            为 ``None`` 时自动查找项目根目录的 ``params.yml``。

    Returns:
        退出码（始终为 0）。

    [EN] Interactive CLI main entry point.

    Args:
        params_path: Optional params.yml path to auto-load on startup.
            When ``None``, automatically looks for ``params.yml`` in the project root.

    Returns:
        Exit code (always 0).
    """
    if params_path is None:
        params_path = _find_default_params()
    cli = InteractiveCLI(params_path)
    try:
        cli.cmdloop()
    except KeyboardInterrupt:
        print(_info("\n" + tr("icli_goodbye", "👋 再见！")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
