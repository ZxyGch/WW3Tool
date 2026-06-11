"""无界面预处理与后处理的命令行适配器。

本模块属于 ``interfaces/`` 入口层，解析 ``runCLI.py`` 传入的子命令与参数，
加载 ``params.yml`` 后委派给 ``application/`` 对应用例执行。

命令分组：
- 预处理：``validate``、``prepare-forcing``、``generate-grid``、``run``
- 后处理/绘图：``plot*``、``match-jason3``、``jason3-swh``、``download-jason3``、``match-ndbc``
- 远程运维：``connect-test``、``upload``、``submit`` 等 SLURM/SSH 操作
- 辅助：``print-example`` 输出示例 YAML

主要消费者：
- 仓库根目录 ``runCLI.py``（``main()`` 的实际入口）
"""

from __future__ import annotations

import argparse
import sys

from ..application.configuration import ConfigError, EXAMPLE_YAML, load_pipeline_config
from ..support.translations import tr


def build_parser() -> argparse.ArgumentParser:
    """构造 ``runCLI.py`` 使用的 argparse 解析器及全部子命令。

    Returns:
        已注册所有子命令与参数的 ``ArgumentParser`` 实例。
    """
    parser = argparse.ArgumentParser(prog="python3 runCLI.py")
    sub = parser.add_subparsers(dest="command", required=True)

    # ── preprocessing ──────────────────────────────────────────────────────
    p_validate = sub.add_parser("validate", help=tr("cli_help_validate", "Validate a YAML parameter file"))
    p_validate.add_argument("params", help=tr("cli_help_params_path", "Path to params.yml"))
    p_validate.add_argument(
        "--stage",
        choices=["forcing", "grid", "full"],
        default="full",
        help=tr("cli_help_validation_scope", "Validation scope"),
    )

    p_forcing = sub.add_parser("prepare-forcing", help=tr("cli_help_prepare_forcing", "Run only forcing preparation"))
    p_forcing.add_argument("params", help=tr("cli_help_params_path", "Path to params.yml"))

    p_grid = sub.add_parser("generate-grid", help=tr("cli_help_generate_grid", "Run only grid generation"))
    p_grid.add_argument("params", help=tr("cli_help_params_path", "Path to params.yml"))
    p_grid.add_argument(
        "--no-cache",
        action="store_true",
        help=tr("cli_help_no_cache", "Force grid generation and do not read or write grid cache"),
    )

    p_run = sub.add_parser("run", help=tr("cli_help_run", "Run headless preprocessing"))
    p_run.add_argument("params", help=tr("cli_help_params_path", "Path to params.yml"))
    p_run.add_argument(
        "--skip-grid",
        action="store_true",
        help=tr("cli_help_skip_grid", "Skip grid generation and use existing grid files in the workdir"),
    )
    p_run.add_argument(
        "--no-cache",
        action="store_true",
        help=tr("cli_help_no_cache", "Force grid generation and do not read or write grid cache"),
    )

    # ── post-processing / plotting ─────────────────────────────────────────
    p_plot = sub.add_parser(
        "plot",
        help=tr("cli_help_plot", "Run all enabled plot tasks from params.yml plot: section"),
    )
    p_plot.add_argument("params", help=tr("cli_help_params_path", "Path to params.yml"))

    p_wm = sub.add_parser("plot-wave-maps", help=tr("cli_help_plot_wave_maps", "Generate wave height filled-color maps"))
    p_wm.add_argument("params", help=tr("cli_help_params_path", "Path to params.yml"))
    p_wm.add_argument(
        "--contour",
        action="store_true",
        help=tr("cli_help_contour", "Generate contour maps instead of filled-color maps"),
    )

    p_sp = sub.add_parser("plot-spectrum", help=tr("cli_help_plot_spectrum", "Generate 2-D spectrum plots"))
    p_sp.add_argument("params", help=tr("cli_help_params_path", "Path to params.yml"))
    p_sp.add_argument(
        "--mode",
        choices=["first", "all", "selected"],
        default="all",
        help=tr("cli_help_spectrum_mode", "Which spectrum frames to plot (default: all)"),
    )
    p_sp.add_argument(
        "--station",
        type=int,
        default=0,
        metavar="INDEX",
        help=tr("cli_help_station", "Station index when --mode=selected"),
    )

    p_j3 = sub.add_parser("match-jason3", help=tr("cli_help_match_jason3", "Match WW3 output to Jason-3 satellite data"))
    p_j3.add_argument("params", help=tr("cli_help_params_path", "Path to params.yml"))

    p_j3swh = sub.add_parser(
        "jason3-swh",
        help=tr("cli_help_jason3_swh", "Plot Jason-3 satellite SWH / track map for the configured region"),
    )
    p_j3swh.add_argument("params", help=tr("cli_help_params_path", "Path to params.yml"))

    p_j3dl = sub.add_parser(
        "download-jason3",
        help=tr("cli_help_download_jason3", "Download Jason-3 L2 data for the configured time range"),
    )
    p_j3dl.add_argument("params", help=tr("cli_help_params_path", "Path to params.yml"))

    p_ndbc = sub.add_parser("match-ndbc", help=tr("cli_help_match_ndbc", "Match WW3 output to NDBC buoy observations"))
    p_ndbc.add_argument("params", help=tr("cli_help_params_path", "Path to params.yml"))
    p_ndbc.add_argument(
        "--download",
        action="store_true",
        help=tr("cli_help_download_ndbc", "Download NDBC data instead of matching"),
    )

    # ── remote server operations ───────────────────────────────────────────
    p_conn = sub.add_parser("connect-test", help=tr("cli_help_connect_test", "Test SSH connection to the server"))
    p_conn.add_argument("params", help=tr("cli_help_params_path", "Path to params.yml"))

    p_ls = sub.add_parser("list-files", help=tr("cli_help_list_files", "List files in the remote workdir"))
    p_ls.add_argument("params", help=tr("cli_help_params_path", "Path to params.yml"))

    p_upload = sub.add_parser(
        "upload",
        help=tr("cli_help_upload", "Upload the local workdir to the remote server (requires --confirm)"),
    )
    p_upload.add_argument("params", help=tr("cli_help_params_path", "Path to params.yml"))
    p_upload.add_argument(
        "--confirm",
        action="store_true",
        help=tr("cli_help_confirm_upload", "Confirm the upload (required - prevents accidental uploads)"),
    )

    p_submit = sub.add_parser("submit", help=tr("cli_help_submit", "Execute a script on the remote server"))
    p_submit.add_argument("params", help=tr("cli_help_params_path", "Path to params.yml"))
    p_submit.add_argument(
        "--script",
        default="server.sh",
        metavar="SCRIPT",
        help=tr("cli_help_script", "Script filename in the remote workdir (default: server.sh)"),
    )

    p_status = sub.add_parser("check-status", help=tr("cli_help_check_status", "Check remote job completion status"))
    p_status.add_argument("params", help=tr("cli_help_params_path", "Path to params.yml"))

    p_queue = sub.add_parser("queue-status", help=tr("cli_help_queue_status", "Show SLURM queue (squeue -l)"))
    p_queue.add_argument("params", help=tr("cli_help_params_path", "Path to params.yml"))

    p_dl = sub.add_parser("download-results", help=tr("cli_help_download_results", "Download ww3*.nc output from remote server"))
    p_dl.add_argument("params", help=tr("cli_help_params_path", "Path to params.yml"))
    p_dl.add_argument(
        "--nested",
        action="store_true",
        help=tr("cli_help_nested_download", "Download from the remote fine/ subdirectory (nested grid)"),
    )

    p_log = sub.add_parser("download-log", help=tr("cli_help_download_log", "Download success.log / fail.log from remote server"))
    p_log.add_argument("params", help=tr("cli_help_params_path", "Path to params.yml"))

    p_clear = sub.add_parser(
        "clear-remote",
        help=tr("cli_help_clear_remote", "Delete all files in the remote workdir (requires --confirm)"),
    )
    p_clear.add_argument("params", help=tr("cli_help_params_path", "Path to params.yml"))
    p_clear.add_argument(
        "--confirm",
        action="store_true",
        help=tr("cli_help_confirm_delete", "Confirm the deletion (required - this operation is irreversible)"),
    )

    p_cancel = sub.add_parser("cancel-job", help=tr("cli_help_cancel_job", "Cancel a SLURM job by id"))
    p_cancel.add_argument("params", help=tr("cli_help_params_path", "Path to params.yml"))
    p_cancel.add_argument("job_id", help=tr("cli_help_job_id", "SLURM job id to cancel"))

    sub.add_parser("print-example", help=tr("cli_help_print_example", "Print an example YAML parameter file"))
    return parser


# 仅需 plot 段校验、跳过预处理必填项的命令集合
_PLOT_COMMANDS = {
    "plot", "plot-wave-maps", "plot-spectrum",
    "match-jason3", "jason3-swh", "download-jason3", "match-ndbc",
}
# 远程 SSH/SLURM 操作命令集合
_REMOTE_COMMANDS = {
    "connect-test", "list-files", "upload", "submit", "check-status",
    "queue-status", "download-results", "download-log",
    "clear-remote", "cancel-job",
}


def main(argv: list[str] | None = None) -> int:
    """CLI 主入口：解析命令、加载配置并执行对应用例。

    Args:
        argv: 命令行参数列表；``None`` 时使用 ``sys.argv[1:]``。

    Returns:
        进程退出码：``0`` 成功，``1`` 运行时异常，``2`` 参数/配置错误，
        ``3`` 破坏性远程操作未加 ``--confirm``。
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "print-example":
        print(EXAMPLE_YAML, end="")
        return 0

    try:
        # Plot and remote commands skip preprocessing validation
        if args.command in _PLOT_COMMANDS or args.command in _REMOTE_COMMANDS:
            stage = "plot"
        else:
            stage = getattr(args, "stage", "full")
        if args.command == "prepare-forcing":
            stage = "forcing"
        if args.command == "generate-grid":
            stage = "grid"

        config = load_pipeline_config(args.params, validation_stage=stage)

        if args.command == "validate":
            print(tr("cli_validate_ok", "OK: {path}").format(path=args.params))
            return 0

        if args.command == "prepare-forcing":
            from ..application.preprocessing_workflow import run_prepare_forcing
            run_prepare_forcing(config, log=print)
            return 0

        if args.command == "generate-grid":
            from ..application.grid_preparation import run_generate_grid
            run_generate_grid(config, log=print, use_cache=not args.no_cache)
            return 0

        if args.command == "run":
            from ..application.preprocessing_workflow import run_pipeline
            run_pipeline(
                config,
                log=print,
                skip_grid=args.skip_grid,
                use_grid_cache=not args.no_cache,
            )
            return 0

        if args.command == "plot":
            return _run_all_plots(config)

        if args.command == "plot-wave-maps":
            return _run_wave_maps(config, contour=args.contour)

        if args.command == "plot-spectrum":
            return _run_spectrum(config, mode=args.mode, station_index=args.station)

        if args.command == "match-jason3":
            return _run_match_jason3(config)

        if args.command == "jason3-swh":
            return _run_jason3_swh(config)

        if args.command == "download-jason3":
            return _run_download_jason3(config)

        if args.command == "match-ndbc":
            return _run_match_ndbc(config, download=args.download)

        if args.command == "connect-test":
            return _remote(lambda: __import__(
                "workflows.application.remote_ops", fromlist=["run_connect_test"]
            ).run_connect_test(config, log=print))

        if args.command == "list-files":
            return _remote(lambda: __import__(
                "workflows.application.remote_ops", fromlist=["run_list_files"]
            ).run_list_files(config, log=print))

        if args.command == "upload":
            return _remote_destructive(
                lambda: __import__(
                    "workflows.application.remote_ops", fromlist=["run_upload"]
                ).run_upload(config, log=print, confirmed=args.confirm),
                confirmed=args.confirm,
                name="upload",
            )

        if args.command == "submit":
            return _remote(lambda: __import__(
                "workflows.application.remote_ops", fromlist=["run_submit"]
            ).run_submit(config, log=print, script=args.script))

        if args.command == "check-status":
            return _remote(lambda: __import__(
                "workflows.application.remote_ops", fromlist=["run_check_status"]
            ).run_check_status(config, log=print))

        if args.command == "queue-status":
            return _remote(lambda: __import__(
                "workflows.application.remote_ops", fromlist=["run_queue_status"]
            ).run_queue_status(config, log=print))

        if args.command == "download-results":
            return _remote(lambda: __import__(
                "workflows.application.remote_ops", fromlist=["run_download_results"]
            ).run_download_results(config, log=print, nested=args.nested))

        if args.command == "download-log":
            return _remote(lambda: __import__(
                "workflows.application.remote_ops", fromlist=["run_download_log"]
            ).run_download_log(config, log=print))

        if args.command == "clear-remote":
            return _remote_destructive(
                lambda: __import__(
                    "workflows.application.remote_ops", fromlist=["run_clear_remote"]
                ).run_clear_remote(config, log=print, confirmed=args.confirm),
                confirmed=args.confirm,
                name="clear-remote",
            )

        if args.command == "cancel-job":
            return _remote(lambda: __import__(
                "workflows.application.remote_ops", fromlist=["run_cancel_job"]
            ).run_cancel_job(config, args.job_id, log=print))

    except ConfigError as exc:
        print(tr("cli_config_error", "参数错误：{error}").format(error=exc), file=sys.stderr)
        return 2
    except Exception as exc:
        print(tr("cli_execution_failed", "执行失败：{error}").format(error=exc), file=sys.stderr)
        return 1

    parser.error(tr("cli_unknown_command", "未知命令：{command}").format(command=args.command))
    return 2


def _run_all_plots(config) -> int:
    """按 ``plot:`` 段各子任务 ``enabled`` 标志依次执行绘图/匹配。

    Args:
        config: 已解析的 ``PipelineConfig``。

    Returns:
        各子任务退出码的最大值（任一失败则非零）。
    """
    rc = 0
    cfg = config.plot
    if cfg.wave_maps.enabled:
        rc = max(rc, _run_wave_maps(config, contour=False))
    if cfg.spectrum.enabled:
        rc = max(rc, _run_spectrum(config))
    if cfg.jason3.enabled:
        rc = max(rc, _run_match_jason3(config))
    if cfg.ndbc.enabled:
        if cfg.ndbc.download:
            rc = max(rc, _run_download_ndbc(config))
        else:
            rc = max(rc, _run_match_ndbc(config))
    return rc


def _run_wave_maps(config, *, contour: bool = False) -> int:
    """生成波高填色图或等值线图。

    Args:
        config: 已解析的 ``PipelineConfig``。
        contour: ``True`` 时使用等值线模式，否则为填色图。

    Returns:
        ``0`` 成功，``1`` 生成失败。
    """
    if contour:
        from ..application.plot_wave_maps import run_contour_maps
        result = run_contour_maps(config, log=print)
    else:
        from ..application.plot_wave_maps import run_wave_maps
        result = run_wave_maps(config, log=print)
    if not result.success:
        print(tr("cli_generation_failed", "生成失败：{error}").format(error=result.error), file=sys.stderr)
        return 1
    return 0


def _run_spectrum(config, *, mode: str = "all", station_index: int = 0) -> int:
    """生成二维方向谱图。

    Args:
        config: 已解析的 ``PipelineConfig``。
        mode: ``first`` / ``all`` / ``selected``，控制绘制的时间帧范围。
        station_index: ``mode=selected`` 时使用的站点索引。

    Returns:
        ``0`` 成功，``1`` 生成失败。
    """
    from ..application.plot_spectrum import run_spectrum
    result = run_spectrum(config, log=print, mode=mode, station_index=station_index)
    if not result.success:
        print(tr("cli_generation_failed", "生成失败：{error}").format(error=result.error), file=sys.stderr)
        return 1
    return 0


def _run_match_jason3(config) -> int:
    """将 WW3 输出与 Jason-3 卫星数据做时空匹配。

    Returns:
        ``0`` 成功，``1`` 匹配失败。
    """
    from ..application.match_jason3 import run_match_jason3
    result = run_match_jason3(config, log=print)
    if not result.success:
        print(tr("cli_matching_failed", "匹配失败：{error}").format(error=result.error), file=sys.stderr)
        return 1
    return 0


def _run_jason3_swh(config) -> int:
    """绘制 Jason-3 卫星 SWH / 轨迹分布图。

    Returns:
        ``0`` 成功，``1`` 生成失败。
    """
    from ..application.match_jason3 import run_jason3_swh
    result = run_jason3_swh(config, log=print)
    if not result.success:
        print(tr("cli_generation_failed", "生成失败：{error}").format(error=result.error), file=sys.stderr)
        return 1
    return 0


def _run_download_jason3(config) -> int:
    """按配置时间范围下载 Jason-3 L2 数据。

    Returns:
        ``0`` 成功，``1`` 下载失败。
    """
    from ..application.download_jason3 import run_download_jason3
    result = run_download_jason3(config, log=print)
    if not result.success:
        print(tr("cli_generation_failed", "生成失败：{error}").format(error=result.error), file=sys.stderr)
        return 1
    return 0


def _run_match_ndbc(config, *, download: bool = False) -> int:
    """将 WW3 输出与 NDBC 浮标观测匹配，或在 ``download=True`` 时仅下载数据。

    Returns:
        ``0`` 成功，``1`` 匹配失败。
    """
    if download:
        return _run_download_ndbc(config)
    from ..application.match_ndbc import run_match_ndbc
    result = run_match_ndbc(config, log=print)
    if not result.success:
        print(tr("cli_matching_failed", "匹配失败：{error}").format(error=result.error), file=sys.stderr)
        return 1
    return 0


def _remote(fn) -> int:
    """执行远程用例并统一处理 ``success`` / ``error`` 结果。

    Args:
        fn: 无参 callable，返回带 ``success`` 与 ``error`` 属性的结果对象。

    Returns:
        ``0`` 成功，``1`` 操作失败。
    """
    result = fn()
    if not result.success:
        print(tr("cli_operation_failed", "操作失败：{error}").format(error=result.error), file=sys.stderr)
        return 1
    return 0


def _remote_destructive(fn, *, confirmed: bool, name: str) -> int:
    """包装需显式 ``--confirm`` 的远程破坏性操作。

    Args:
        fn: 已通过确认后应执行的远程用例 callable。
        confirmed: 用户是否在命令行传入 ``--confirm``。
        name: 子命令名，用于错误提示。

    Returns:
        ``0`` 成功，``1`` 操作失败，``3`` 未确认。
    """
    if not confirmed:
        print(
            tr("cli_destructive_requires_confirm", "错误：{name} 是破坏性操作，必须加 --confirm 才能执行。").format(name=name),
            file=sys.stderr,
        )
        return 3
    return _remote(fn)


def _run_download_ndbc(config) -> int:
    """从 NDBC 下载浮标观测数据。

    Returns:
        ``0`` 成功，``1`` 下载失败。
    """
    from ..application.match_ndbc import run_download_ndbc
    result = run_download_ndbc(config, log=print)
    if not result.success:
        print(tr("cli_download_failed", "下载失败：{error}").format(error=result.error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
