"""无界面预处理与后处理的命令行适配器。

本模块属于 ``interfaces/`` 入口层，解析 ``run.py`` 传入的子命令与参数，
从指定工作目录中加载 ``params.yml`` 后委派给 ``application/`` 对应用例执行。

**工作目录约定**：根目录 ``params.yml`` 仅作为模板，CLI 不允许直接使用。
所有子命令接受一个 ``workdir`` 参数（含 ``params.yml`` 的目录），
省略时使用当前目录。用 ``workdir <路径>`` 从模板创建或加载工作目录。

命令分组：
- 配置管理：``workdir``、``validate``、``config``、``print-params``
- 预处理：``prepare-forcing``、``merge-forcing``、``generate-grid``、``prepare-ww3``、``recommend-cfl``、``recommend-grid``、``run-workflow``、``local-run``
- 后处理/绘图：``plot-wave-maps``、``plot-spectrum``、``plot-jason3``、``plot-jason3-swh``、``download-jason3``、``plot-ndbc``
- 远程运维：``connect-test``、``ssh``、``upload``、``submit``、``ntfy-watch``、``ntfy-watch-job`` 等 SLURM/SSH 操作
- 辅助：``print-example`` 输出示例 YAML

主要消费者：
- 仓库根目录 ``run.py``（``main()`` 的实际入口）

[EN] Command-line adapter for headless preprocessing and post-processing.

This module belongs to the ``interfaces/`` entry-point layer. It parses subcommands
and arguments passed from ``run.py``, loads ``params.yml`` from the specified
working directory, and delegates to the corresponding ``application/`` use case.

**Working directory convention**: The root ``params.yml`` is only a template and
cannot be used directly by the CLI. All subcommands accept a ``workdir`` argument
(directory containing ``params.yml``); the current directory is used when omitted.
Use ``workdir <path>`` to create or load a working directory from the template first.

Command groups:
- Configuration: ``workdir``, ``validate``, ``config``, ``print-params``
- Preprocessing: ``prepare-forcing``, ``merge-forcing``, ``generate-grid``, ``prepare-ww3``, ``recommend-cfl``, ``recommend-grid``, ``run-workflow``, ``local-run``
- Post-processing/plotting: ``plot-wave-maps``, ``plot-spectrum``, ``plot-jason3``, ``plot-jason3-swh``, ``download-jason3``, ``plot-ndbc``
- Remote operations: ``connect-test``, ``ssh``, ``upload``, ``submit`` and other SLURM/SSH operations
- Auxiliary: ``print-example`` outputs a sample YAML

Main consumers:
- Repository root ``run.py`` (the actual entry point of ``main()``)
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from ..application.configuration import ConfigError, EXAMPLE_YAML, load_pipeline_config
from ..support.translations import tr


def _repo_root_path() -> Path:
    """返回仓库根目录的绝对路径。

    [EN] Return the absolute path of the repository root directory.
    """
    return Path(__file__).resolve().parents[3]


def _is_root_params(path: Path) -> bool:
    """判断 *path* 是否指向仓库根目录的 params.yml（模板文件）。

    [EN] Check whether *path* points to the repository root params.yml (template file).
    """
    root_params = _repo_root_path() / "params.yml"
    try:
        return os.path.normpath(str(path.resolve())) == os.path.normpath(str(root_params))
    except OSError:
        return False


def resolve_params_path(workdir_arg: str | None) -> str:
    """从工作目录参数解析 params.yml 的绝对路径。

    - 若 *workdir_arg* 是文件路径，直接使用该文件。
    - 若 *workdir_arg* 是目录，查找其中的 ``params.yml``。
    - 若为 ``None``，使用当前工作目录。

    Raises:
        ConfigError: 工作目录中无 ``params.yml``，或路径指向根目录模板。

    [EN] Resolve the absolute path of params.yml from the working directory argument.

    - If *workdir_arg* is a file path, use that file directly.
    - If *workdir_arg* is a directory, look for ``params.yml`` inside it.
    - If ``None``, use the current working directory.

    Raises:
        ConfigError: No ``params.yml`` in the working directory, or the path points to the root template.
    """
    if workdir_arg is not None:
        p = Path(workdir_arg).resolve()
    else:
        p = Path.cwd()

    if p.is_file():
        params_path = p
    else:
        params_path = p / "params.yml"
        if not params_path.is_file():
            raise ConfigError(
                tr(
                    "cli_workdir_no_params",
                    "工作目录 {workdir} 中没有 params.yml。"
                    "请先使用 workdir 命令创建或加载工作目录。",
                ).format(workdir=p)
            )

    if _is_root_params(params_path):
        raise ConfigError(
            tr(
                "cli_root_params_rejected",
                "不允许直接使用仓库根目录的 params.yml（它是模板文件）。\n"
                "请先使用 workdir 命令创建或加载工作目录：\n"
                "  python3 run.py workdir my_workdir",
            )
        )

    return str(params_path)


def build_parser() -> argparse.ArgumentParser:
    """构造 ``run.py`` 使用的 argparse 解析器及全部子命令。

    Returns:
        已注册所有子命令与参数的 ``ArgumentParser`` 实例。

    [EN] Build the argparse parser used by ``run.py`` with all subcommands.

    Returns:
        An ``ArgumentParser`` instance with all subcommands and arguments registered.
    """
    parser = argparse.ArgumentParser(prog="python3 run.py")
    sub = parser.add_subparsers(dest="command", required=True)

    # ── configuration ──────────────────────────────────────────────────────
    _WD_HELP = tr("cli_help_workdir", "Working directory containing params.yml (default: current directory)")

    p_workdir = sub.add_parser(
        "workdir",
        help=tr("cli_help_workdir_cmd", "Create or load a working directory from the root params.yml template"),
    )
    p_workdir.add_argument(
        "path",
        metavar="PATH",
        help=tr("cli_help_workdir_path", "Working directory path to create or load"),
    )

    p_validate = sub.add_parser("validate", help=tr("cli_help_validate", "Validate a YAML parameter file"))
    p_validate.add_argument("workdir", nargs="?", default=None, help=_WD_HELP)

    p_config = sub.add_parser("config", help=tr("cli_help_config", "Show a configuration summary"))
    p_config.add_argument("workdir", nargs="?", default=None, help=_WD_HELP)

    p_print_params = sub.add_parser(
        "print-params",
        help=tr("cli_help_print_params", "Print params.yml from the working directory"),
    )
    p_print_params.add_argument("workdir", nargs="?", default=None, help=_WD_HELP)

    # ── preprocessing ──────────────────────────────────────────────────────
    p_forcing = sub.add_parser("prepare-forcing", help=tr("cli_help_prepare_forcing", "Run only forcing preparation"))
    p_forcing.add_argument("workdir", nargs="?", default=None, help=_WD_HELP)

    p_merge = sub.add_parser(
        "merge-forcing",
        help=tr(
            "cli_help_merge_forcing",
            "Validate and merge NetCDF forcing files (standalone; no workdir needed)",
        ),
    )
    p_merge.add_argument(
        "inputs",
        nargs="+",
        metavar="INPUT",
        help=tr("cli_help_merge_forcing_inputs", "Input NetCDF forcing files"),
    )
    p_merge.add_argument(
        "-o",
        "--output",
        required=True,
        metavar="OUTPUT",
        help=tr("cli_help_merge_forcing_output", "Output NetCDF file"),
    )
    p_merge.add_argument(
        "--time-range",
        nargs=2,
        metavar=("START", "END"),
        default=None,
        help=tr(
            "cli_help_merge_forcing_time_range",
            "Clip output to [START, END] (YYYYMMDD or ISO time); default: union of all inputs",
        ),
    )
    p_merge.add_argument(
        "--bbox",
        nargs=4,
        type=float,
        metavar=("WEST", "EAST", "SOUTH", "NORTH"),
        default=None,
        help=tr(
            "cli_help_merge_forcing_bbox",
            "Clip output to lon/lat extent west east south north; default: common grid (min extent)",
        ),
    )

    p_grid = sub.add_parser("generate-grid", help=tr("cli_help_generate_grid", "Run only grid generation"))
    p_grid.add_argument("workdir", nargs="?", default=None, help=_WD_HELP)

    p_recgrid = sub.add_parser(
        "recommend-grid",
        help=tr("cli_help_recommend_grid", "Recommend grid spacing/resolution from the domain extent and write to params.yml"),
    )
    p_recgrid.add_argument("workdir", nargs="?", default=None, help=_WD_HELP)
    p_recgrid.add_argument(
        "--coarse", action="store_true",
        help=tr("cli_help_recommend_grid_coarse", "Use one tier coarser than the auto-matched recommendation"),
    )
    p_recgrid.add_argument(
        "--fine", action="store_true",
        help=tr("cli_help_recommend_grid_fine", "Use one tier finer than the auto-matched recommendation"),
    )

    p_run = sub.add_parser(
        "run-workflow",
        help=tr("cli_help_run_workflow", "Run full preprocessing (forcing → grid → WW3 namelist)"),
    )
    p_run.add_argument("workdir", nargs="?", default=None, help=_WD_HELP)

    p_prepare_ww3 = sub.add_parser(
        "prepare-ww3",
        help=tr("cli_help_prepare_ww3", "Generate WW3 namelist only (skip forcing and grid)"),
    )
    p_prepare_ww3.add_argument("workdir", nargs="?", default=None, help=_WD_HELP)

    p_rec_cfl = sub.add_parser(
        "recommend-cfl",
        help=tr("cli_help_recommend_cfl", "Recommend timesteps via CFL and write back to params.yml"),
    )
    p_rec_cfl.add_argument("workdir", nargs="?", default=None, help=_WD_HELP)

    p_local_run = sub.add_parser(
        "local-run",
        help=tr("cli_help_local_run", "Execute local.sh in the working directory"),
    )
    p_local_run.add_argument("workdir", nargs="?", default=None, help=_WD_HELP)

    # ── post-processing / plotting ─────────────────────────────────────────
    p_wm = sub.add_parser("plot-wave-maps", help=tr("cli_help_plot_wave_maps", "Generate wave height filled-color maps"))
    p_wm.add_argument("workdir", nargs="?", default=None, help=_WD_HELP)
    p_wm.add_argument(
        "--contour",
        action="store_true",
        help=tr("cli_help_contour", "Generate contour maps instead of filled-color maps"),
    )

    p_sp = sub.add_parser("plot-spectrum", help=tr("cli_help_plot_spectrum", "Generate 2-D spectrum plots"))
    p_sp.add_argument("workdir", nargs="?", default=None, help=_WD_HELP)
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

    p_j3 = sub.add_parser("plot-jason3", help=tr("cli_help_match_jason3", "Match WW3 output to Jason-3 satellite data"))
    p_j3.add_argument("workdir", nargs="?", default=None, help=_WD_HELP)

    p_j3swh = sub.add_parser(
        "plot-jason3-swh",
        help=tr("cli_help_jason3_swh", "Plot Jason-3 satellite SWH / track map for the configured region"),
    )
    p_j3swh.add_argument("workdir", nargs="?", default=None, help=_WD_HELP)

    p_j3dl = sub.add_parser(
        "download-jason3",
        help=tr("cli_help_download_jason3", "Download Jason-3 L2 data for the configured time range"),
    )
    p_j3dl.add_argument("workdir", nargs="?", default=None, help=_WD_HELP)

    p_ndbc = sub.add_parser("plot-ndbc", help=tr("cli_help_match_ndbc", "Match WW3 output to NDBC buoy observations"))
    p_ndbc.add_argument("workdir", nargs="?", default=None, help=_WD_HELP)
    p_ndbc.add_argument(
        "--download",
        action="store_true",
        help=tr("cli_help_download_ndbc", "Download NDBC data instead of matching"),
    )

    # ── remote server operations ───────────────────────────────────────────
    p_conn = sub.add_parser("connect-test", help=tr("cli_help_connect_test", "Test SSH connection to the server"))
    p_conn.add_argument("workdir", nargs="?", default=None, help=_WD_HELP)

    p_ssh = sub.add_parser("ssh", help=tr("cli_help_ssh", "Open an interactive SSH terminal"))
    p_ssh.add_argument("workdir", nargs="?", default=None, help=_WD_HELP)

    p_slurm_idle = sub.add_parser(
        "slurm-idle",
        help=tr("cli_help_slurm_idle", "Query Slurm idle CPU resources on the remote server"),
    )
    p_slurm_idle.add_argument("workdir", nargs="?", default=None, help=_WD_HELP)

    p_confirm_slurm = sub.add_parser(
        "confirm-slurm",
        help=tr(
            "cli_help_confirm_slurm",
            "Write params.yml Slurm settings to server.sh (optional --full/--half to auto-pick idle CPUs)",
        ),
    )
    p_confirm_slurm.add_argument("workdir", nargs="?", default=None, help=_WD_HELP)
    p_confirm_slurm.add_argument(
        "--full",
        action="store_true",
        help=tr("cli_help_confirm_slurm_full", "Use the largest idle CPU partition (same as GUI full use)"),
    )
    p_confirm_slurm.add_argument(
        "--half",
        action="store_true",
        help=tr("cli_help_confirm_slurm_half", "Use half of the largest idle CPU partition (same as GUI half use)"),
    )

    p_ls = sub.add_parser("list-files", help=tr("cli_help_list_files", "List files in the remote workdir"))
    p_ls.add_argument("workdir", nargs="?", default=None, help=_WD_HELP)

    p_upload = sub.add_parser(
        "upload",
        help=tr("cli_help_upload", "Upload the local workdir to the remote server (requires --confirm)"),
    )
    p_upload.add_argument("workdir", nargs="?", default=None, help=_WD_HELP)
    p_upload.add_argument(
        "--confirm",
        action="store_true",
        help=tr("cli_help_confirm_upload", "Confirm the upload (required - prevents accidental uploads)"),
    )

    p_submit = sub.add_parser("submit", help=tr("cli_help_submit", "Execute a script on the remote server"))
    p_submit.add_argument("workdir", nargs="?", default=None, help=_WD_HELP)
    p_submit.add_argument(
        "--script",
        default="server.sh",
        metavar="SCRIPT",
        help=tr("cli_help_script", "Script filename in the remote workdir (default: server.sh)"),
    )

    p_status = sub.add_parser("check-status", help=tr("cli_help_check_status", "Check remote job completion status"))
    p_status.add_argument("workdir", nargs="?", default=None, help=_WD_HELP)

    p_queue = sub.add_parser("queue-status", help=tr("cli_help_queue_status", "Show SLURM queue (squeue -l)"))
    p_queue.add_argument("workdir", nargs="?", default=None, help=_WD_HELP)

    p_dl = sub.add_parser("download-results", help=tr("cli_help_download_results", "Download ww3*.nc output from remote server"))
    p_dl.add_argument("workdir", nargs="?", default=None, help=_WD_HELP)
    p_dl.add_argument(
        "--nested",
        action="store_true",
        help=tr("cli_help_nested_download", "Download from the remote fine/ subdirectory (nested grid)"),
    )

    p_log = sub.add_parser("download-log", help=tr("cli_help_download_log", "Download success.log / fail.log from remote server"))
    p_log.add_argument("workdir", nargs="?", default=None, help=_WD_HELP)

    p_clear = sub.add_parser(
        "clear-remote",
        help=tr("cli_help_clear_remote", "Delete all files in the remote workdir (requires --confirm)"),
    )
    p_clear.add_argument("workdir", nargs="?", default=None, help=_WD_HELP)
    p_clear.add_argument(
        "--confirm",
        action="store_true",
        help=tr("cli_help_confirm_delete", "Confirm the deletion (required - this operation is irreversible)"),
    )

    p_cancel = sub.add_parser("cancel-job", help=tr("cli_help_cancel_job", "Cancel a SLURM job by id"))
    p_cancel.add_argument("workdir", nargs="?", default=None, help=_WD_HELP)
    p_cancel.add_argument("job_id", nargs="?", default=None, help=tr("cli_help_job_id", "SLURM job id to cancel"))

    p_ntfy = sub.add_parser(
        "ntfy-watch",
        help=tr("cli_help_ntfy_watch", "Inject a persistent ntfy watcher on the remote login node"),
    )
    p_ntfy.add_argument("workdir", nargs="?", default=None, help=_WD_HELP)

    p_ntfy_job = sub.add_parser(
        "ntfy-watch-job",
        help=tr("cli_help_ntfy_watch_job", "Inject a one-shot ntfy watcher for a specific SLURM job"),
    )
    p_ntfy_job.add_argument("workdir", nargs="?", default=None, help=_WD_HELP)
    p_ntfy_job.add_argument(
        "job_id",
        help=tr("cli_help_ntfy_job_id", "SLURM job id to watch"),
    )

    sub.add_parser("print-example", help=tr("cli_help_print_example", "Print an example YAML parameter file"))
    return parser


# 仅需 plot 段校验、跳过预处理必填项的命令集合
# [EN] Commands that only require plot-stage validation, skipping preprocessing prerequisites
_PLOT_COMMANDS = {
    "plot-wave-maps", "plot-spectrum",
    "plot-jason3", "plot-jason3-swh", "download-jason3", "plot-ndbc",
}
# 远程 SSH/SLURM 操作命令集合
# [EN] Remote SSH/SLURM operation commands
_REMOTE_COMMANDS = {
    "connect-test", "ssh", "slurm-idle", "confirm-slurm", "list-files", "upload", "submit",
    "check-status", "queue-status", "download-results", "download-log",
    "clear-remote", "cancel-job", "ntfy-watch", "ntfy-watch-job",
}



def _run_workdir(path: str) -> int:
    """Create or validate a working directory (shared with shell ``workdir``)."""
    from .workdir_setup import WorkdirError, ensure_workdir

    try:
        workdir, created = ensure_workdir(path)
        if created:
            print(tr("icli_created_workdir", "✅ 已创建工作目录：{}").format(workdir))
        else:
            print(tr("icli_workdir_exists", "ℹ️ 目录已存在，自动加载：{}").format(workdir))
        print(tr("cli_workdir_params", "配置文件：{path}").format(path=workdir / "params.yml"))
        return 0
    except WorkdirError as exc:
        print(str(exc), file=sys.stderr)
        return 1


def main(argv: list[str] | None = None) -> int:
    """CLI 主入口：解析命令、加载配置并执行对应用例。

    Args:
        argv: 命令行参数列表；``None`` 时使用 ``sys.argv[1:]``。

    Returns:
        进程退出码：``0`` 成功，``1`` 运行时异常，``2`` 参数/配置错误，
        ``3`` 破坏性远程操作未加 ``--confirm``。

    [EN] CLI main entry point: parse commands, load configuration, and execute the corresponding use case.

    Args:
        argv: Command-line argument list; uses ``sys.argv[1:]`` when ``None``.

    Returns:
        Process exit code: ``0`` success, ``1`` runtime exception, ``2`` argument/config error,
        ``3`` destructive remote operation without ``--confirm``.
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "print-example":
        print(EXAMPLE_YAML, end="")
        return 0

    if args.command == "workdir":
        return _run_workdir(args.path)

    try:
        if args.command == "merge-forcing":
            return _run_merge_forcing(
                args.inputs, args.output, time_range=args.time_range, bbox=args.bbox
            )

        # cancel-job: job_id 必填
        # [EN] cancel-job: job_id is required
        if args.command == "cancel-job":
            if not getattr(args, "job_id", None):
                print(
                    tr("cli_cancel_requires_job_id", "❌ 错误：cancel-job 需要提供 SLURM job id"),
                    file=sys.stderr,
                )
                return 2

        # 从工作目录解析 params.yml 路径
        # [EN] Resolve params.yml path from the working directory
        params_path = resolve_params_path(getattr(args, "workdir", None))

        # Plot and remote commands skip preprocessing validation
        if args.command in _PLOT_COMMANDS or args.command in _REMOTE_COMMANDS:
            stage = "plot"
        else:
            stage = "full"
        if args.command == "prepare-forcing":
            stage = "forcing"
        if args.command in ("generate-grid", "recommend-grid"):
            stage = "grid"

        config = load_pipeline_config(params_path, validation_stage=stage)

        if args.command == "validate":
            print(tr("cli_validate_ok", "✅ OK: {path}").format(path=params_path))
            return 0

        if args.command == "config":
            from .interactive_cli import print_config_summary

            print_config_summary(config, params_path)
            return 0

        if args.command == "print-params":
            # [EN] Filter out the desktop: section (GUI preferences) — it is not
            # pipeline configuration and should not clutter CLI output.
            # 过滤掉 desktop: 段（GUI 偏好设置），避免混入流水线配置输出。
            text = Path(params_path).read_text(encoding="utf-8")
            lines = text.splitlines(keepends=True)
            out: list[str] = []
            skip = False
            for line in lines:
                stripped = line.lstrip()
                if stripped.startswith("desktop:") and (len(line) - len(stripped)) == 0:
                    skip = True
                    continue
                if skip:
                    if stripped and not stripped.startswith("#") and (len(line) - len(stripped)) == 0:
                        skip = False
                    else:
                        continue
                out.append(line)
            print("".join(out), end="")
            return 0

        if args.command == "prepare-forcing":
            from ..application.preprocessing_workflow import run_prepare_forcing
            run_prepare_forcing(config, log=print)
            return 0

        if args.command == "generate-grid":
            from ..application.grid_preparation import run_generate_grid
            run_generate_grid(config, log=print, use_cache=True)
            return 0

        if args.command == "recommend-grid":
            offset = 1 if args.coarse else (-1 if args.fine else 0)
            return _run_recommend_grid(config, params_path, offset=offset)

        if args.command == "run-workflow":
            from ..application.preprocessing_workflow import run_pipeline
            run_pipeline(
                config,
                log=print,
                skip_grid=False,
                use_grid_cache=True,
            )
            return 0

        if args.command == "prepare-ww3":
            return _run_prepare_ww3(config)

        if args.command == "recommend-cfl":
            return _run_recommend_cfl(config, params_path)

        if args.command == "local-run":
            return _run_local_run(config)

        if args.command == "plot-wave-maps":
            return _run_wave_maps(config, contour=args.contour)

        if args.command == "plot-spectrum":
            return _run_spectrum(config, mode=args.mode, station_index=args.station)

        if args.command == "plot-jason3":
            return _run_match_jason3(config)

        if args.command == "plot-jason3-swh":
            return _run_jason3_swh(config)

        if args.command == "download-jason3":
            return _run_download_jason3(config)

        if args.command == "plot-ndbc":
            return _run_match_ndbc(config, download=args.download)

        if args.command == "connect-test":
            return _remote(lambda: __import__(
                "workflows.application.remote_ops", fromlist=["run_connect_test"]
            ).run_connect_test(config, log=print))

        if args.command == "ssh":
            from .interactive_cli import open_ssh_session

            rc = open_ssh_session(config, log=print)
            return 0 if rc == 0 else 1

        if args.command == "slurm-idle":
            return _remote(lambda: __import__(
                "workflows.application.slurm_ops", fromlist=["run_slurm_idle"]
            ).run_slurm_idle(config, log=print))

        if args.command == "confirm-slurm":
            if args.full and args.half:
                print(
                    tr("cli_confirm_slurm_mode_conflict", "❌ 错误：--full 与 --half 不能同时使用"),
                    file=sys.stderr,
                )
                return 2
            mode = "full" if args.full else ("half" if args.half else None)
            from ..application.slurm_ops import run_confirm_slurm

            return run_confirm_slurm(config, params_path, print, mode=mode)

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

        if args.command == "ntfy-watch":
            return _remote(lambda: __import__(
                "workflows.application.remote_ops", fromlist=["run_inject_ntfy_listener"]
            ).run_inject_ntfy_listener(config, log=print))

        if args.command == "ntfy-watch-job":
            return _remote(lambda: __import__(
                "workflows.application.remote_ops", fromlist=["run_inject_ntfy_job_listener"]
            ).run_inject_ntfy_job_listener(config, args.job_id, log=print))

    except ConfigError as exc:
        print(tr("cli_config_error", "❌ 参数错误：{error}").format(error=exc), file=sys.stderr)
        return 2
    except Exception as exc:
        print(tr("cli_execution_failed", "❌ 执行失败：{error}").format(error=exc), file=sys.stderr)
        return 1

    parser.error(tr("cli_unknown_command", "❌ 未知命令：{command}").format(command=args.command))
    return 2


def _run_prepare_ww3(config) -> int:
    from ..infrastructure.forcing.file_service import FileService
    from ..infrastructure.forcing.use_cases import ScanWorkdirForcingUseCase
    from ..infrastructure.adapters.ww3_namelist_adapter import prepare_ww3_files
    from ..support.logging import CoreLogger

    logger = CoreLogger(callback=print)
    file_service = FileService(logger=logger)
    files = ScanWorkdirForcingUseCase(file_service).execute(str(config.workdir.path))
    prepare_ww3_files(config, files, logger)
    return 0


def _run_recommend_cfl(config, params_path: str) -> int:
    from ..domain.timestep_recommendation import as_ww3_grid_parameters, recommend_timesteps_from_spacing
    from .interactive_cli import _cfl_spacing_from_grid, _extract_freq1, _persist_ww3_grid_timesteps

    grid = config.grid
    dxy_m, reason = _cfl_spacing_from_grid(grid)
    if dxy_m is None:
        if reason == "need_hmin":
            print(tr("icli_cfl_need_hmin", "⚠️ 请先填写有效的非结构网格最小尺度 hmin（km）"), file=sys.stderr)
        else:
            print(tr("icli_cfl_need_grid", "⚠️ 请先在网格配置中填写有效的 DX、DY 与纬度范围"), file=sys.stderr)
        return 1

    freq1 = _extract_freq1(config)
    if freq1 is None:
        print(tr("icli_cfl_need_freq1", "⚠️ 请填写有效的起始频率 FREQ1（Hz）"), file=sys.stderr)
        return 1

    rec = recommend_timesteps_from_spacing(dxy_m=dxy_m, freq1=freq1)
    new_params = as_ww3_grid_parameters(rec)
    config.ww3_grid.parameters.update(new_params)
    _persist_ww3_grid_timesteps(params_path, new_params)

    print(tr("icli_cfl_result", "📐 CFL 推荐时间步长"))
    print(f"  DXY ≈ {rec.dxy_m:.0f} m，Tcfl ≈ {rec.tcfl:.0f} s")
    print(f"  DTXY  = {rec.dtxy} s")
    print(f"  DTMAX = {rec.dtmax} s")
    print(f"  DTKTH = {rec.dtkth} s")
    print(f"  DTMIN = {rec.dtmin} s")
    print(f"  CFL ratio = {rec.cfl_ratio:.2f}")
    print(tr("icli_cfl_persisted", "✅ 已写入 {}").format(params_path))
    return 0


def _run_local_run(config) -> int:
    from ..application.local_run import run_local
    from ..infrastructure.local.run_service import LocalRunService

    result = run_local(config, LocalRunService(), log=print)
    return 0 if result.success else 1


def _run_merge_forcing(
    input_paths: list[str],
    output_path: str,
    *,
    time_range: list[str] | None = None,
    bbox: list[float] | None = None,
) -> int:
    """Validate and merge forcing files while printing progress."""
    from ..application.forcing_merge import run_merge_forcing

    run_merge_forcing(
        input_paths,
        output_path,
        log=print,
        progress=lambda value, message: print(f"{value}% {message}"),
        time_range=time_range,
        bbox=bbox,
    )
    return 0


def _run_all_plots(config) -> int:
    """依次执行所有绘图/匹配子任务。

    Args:
        config: 已解析的 ``PipelineConfig``。

    Returns:
        各子任务退出码的最大值（任一失败则非零）。

    [EN] Execute all plotting/matching sub-tasks in sequence.

    Args:
        config: Resolved ``PipelineConfig``.

    Returns:
        Maximum exit code across all sub-tasks (non-zero if any failed).
    """
    rc = 0
    cfg = config.plot
    rc = max(rc, _run_wave_maps(config, contour=False))
    rc = max(rc, _run_spectrum(config))
    rc = max(rc, _run_match_jason3(config))
    if cfg.ndbc.download:
        rc = max(rc, _run_download_ndbc(config))
    else:
        rc = max(rc, _run_match_ndbc(config))
    return rc


def _run_recommend_grid(config, params_path: str, *, offset: int = 0) -> int:
    """按区域范围推荐网格间距/分辨率，打印并写回 params.yml。

    [EN] Recommend grid spacing/resolution from the domain extent; print and
    persist to params.yml. Returns ``0`` on success, ``1`` when the extent is
    missing/invalid. ``offset`` shifts the tier: +1 coarser, -1 finer.
    """
    from ..domain.grid_spacing_recommendation import recommend_grid_params
    from .interactive_cli import _persist_grid_params

    grid = config.grid
    outer = grid.outer
    if not outer or not outer.lon or not outer.lat:
        print(tr("cli_recgrid_need_box", "❌ 请先在 params.yml 的 grid.outer 中填写有效的经纬度范围"), file=sys.stderr)
        return 1
    lon = [float(outer.lon[0]), float(outer.lon[1])]
    lat = [float(outer.lat[0]), float(outer.lat[1])]

    rec = recommend_grid_params(grid.mesh_type, lon, lat, offset=offset)
    if rec is None:
        print(tr("cli_recgrid_need_box", "❌ 请先在 params.yml 的 grid.outer 中填写有效的经纬度范围"), file=sys.stderr)
        return 1

    _persist_grid_params(params_path, rec.section, rec.values)
    offset_hint = ""
    if offset > 0:
        offset_hint = tr("cli_recgrid_offset_coarse", "（偏粗 {n} 档）").format(n=offset)
    elif offset < 0:
        offset_hint = tr("cli_recgrid_offset_fine", "（偏细 {n} 档）").format(n=-offset)
    print(tr("cli_recgrid_result", "📐 网格参数推荐（{mesh}，跨度≈{span} km）：").format(
        mesh=rec.mesh_type, span=int(rec.span_km)) + offset_hint)
    for key, value in rec.values.items():
        print(f"  {key} = {value}")
    print(tr("cli_recgrid_persisted", "✅ 已写入 {path}").format(path=params_path))
    return 0


def _run_wave_maps(config, *, contour: bool = False) -> int:
    """生成波高填色图或等值线图。

    Args:
        config: 已解析的 ``PipelineConfig``。
        contour: ``True`` 时使用等值线模式，否则为填色图。

    Returns:
        ``0`` 成功，``1`` 生成失败。

    [EN] Generate wave height filled-color or contour maps.

    Args:
        config: Resolved ``PipelineConfig``.
        contour: Use contour mode when ``True``, otherwise filled-color.

    Returns:
        ``0`` on success, ``1`` on generation failure.
    """
    if contour:
        from ..application.plot_wave_maps import run_contour_maps
        result = run_contour_maps(config, log=print)
    else:
        from ..application.plot_wave_maps import run_wave_maps
        result = run_wave_maps(config, log=print)
    if not result.success:
        print(tr("cli_generation_failed", "❌ 生成失败：{error}").format(error=result.error), file=sys.stderr)
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

    [EN] Generate 2-D directional spectrum plots.

    Args:
        config: Resolved ``PipelineConfig``.
        mode: ``first`` / ``all`` / ``selected``, controls the time frame range to plot.
        station_index: Station index used when ``mode=selected``.

    Returns:
        ``0`` on success, ``1`` on generation failure.
    """
    from ..application.plot_spectrum import run_spectrum
    result = run_spectrum(config, log=print, mode=mode, station_index=station_index)
    if not result.success:
        print(tr("cli_generation_failed", "❌ 生成失败：{error}").format(error=result.error), file=sys.stderr)
        return 1
    return 0


def _run_match_jason3(config) -> int:
    """将 WW3 输出与 Jason-3 卫星数据做时空匹配。

    Returns:
        ``0`` 成功，``1`` 匹配失败。

    [EN] Perform spatiotemporal matching of WW3 output with Jason-3 satellite data.

    Returns:
        ``0`` on success, ``1`` on matching failure.
    """
    from ..application.match_jason3 import run_match_jason3
    result = run_match_jason3(config, log=print)
    if not result.success:
        print(tr("cli_matching_failed", "❌ 匹配失败：{error}").format(error=result.error), file=sys.stderr)
        return 1
    return 0


def _run_jason3_swh(config) -> int:
    """绘制 Jason-3 卫星 SWH / 轨迹分布图。

    Returns:
        ``0`` 成功，``1`` 生成失败。

    [EN] Plot Jason-3 satellite SWH / track distribution maps.

    Returns:
        ``0`` on success, ``1`` on generation failure.
    """
    from ..application.match_jason3 import run_jason3_swh
    result = run_jason3_swh(config, log=print)
    if not result.success:
        print(tr("cli_generation_failed", "❌ 生成失败：{error}").format(error=result.error), file=sys.stderr)
        return 1
    return 0


def _run_download_jason3(config) -> int:
    """按配置时间范围下载 Jason-3 L2 数据。

    Returns:
        ``0`` 成功，``1`` 下载失败。

    [EN] Download Jason-3 L2 data for the configured time range.

    Returns:
        ``0`` on success, ``1`` on download failure.
    """
    from ..application.download_jason3 import run_download_jason3
    result = run_download_jason3(config, log=print)
    if not result.success:
        print(tr("cli_generation_failed", "❌ 生成失败：{error}").format(error=result.error), file=sys.stderr)
        return 1
    return 0


def _run_match_ndbc(config, *, download: bool = False) -> int:
    """将 WW3 输出与 NDBC 浮标观测匹配，或在 ``download=True`` 时仅下载数据。

    Returns:
        ``0`` 成功，``1`` 匹配失败。

    [EN] Match WW3 output with NDBC buoy observations, or just download data when ``download=True``.

    Returns:
        ``0`` on success, ``1`` on matching failure.
    """
    if download:
        return _run_download_ndbc(config)
    from ..application.match_ndbc import run_match_ndbc
    result = run_match_ndbc(config, log=print)
    if not result.success:
        print(tr("cli_matching_failed", "❌ 匹配失败：{error}").format(error=result.error), file=sys.stderr)
        return 1
    return 0


def _remote(fn) -> int:
    """执行远程用例并统一处理 ``success`` / ``error`` 结果。

    Args:
        fn: 无参 callable，返回带 ``success`` 与 ``error`` 属性的结果对象。

    Returns:
        ``0`` 成功，``1`` 操作失败。

    [EN] Execute a remote use case and uniformly handle ``success`` / ``error`` results.

    Args:
        fn: No-argument callable returning a result object with ``success`` and ``error`` attributes.

    Returns:
        ``0`` on success, ``1`` on operation failure.
    """
    result = fn()
    if not result.success:
        print(tr("cli_operation_failed", "❌ 操作失败：{error}").format(error=result.error), file=sys.stderr)
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

    [EN] Wrap a remote destructive operation that requires explicit ``--confirm``.

    Args:
        fn: Remote use case callable to execute after confirmation is granted.
        confirmed: Whether the user passed ``--confirm`` on the command line.
        name: Subcommand name, used for error messages.

    Returns:
        ``0`` on success, ``1`` on operation failure, ``3`` if not confirmed.
    """
    if not confirmed:
        print(
            tr("cli_destructive_requires_confirm", "❌ 错误：{name} 是破坏性操作，必须加 --confirm 才能执行。").format(name=name),
            file=sys.stderr,
        )
        return 3
    return _remote(fn)


def _run_download_ndbc(config) -> int:
    """从 NDBC 下载浮标观测数据。

    Returns:
        ``0`` 成功，``1`` 下载失败。

    [EN] Download NDBC buoy observation data.

    Returns:
        ``0`` on success, ``1`` on download failure.
    """
    from ..application.match_ndbc import run_download_ndbc
    result = run_download_ndbc(config, log=print)
    if not result.success:
        print(tr("cli_download_failed", "❌ 下载失败：{error}").format(error=result.error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
