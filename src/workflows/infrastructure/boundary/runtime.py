"""脚本共用的边界执行入口：``python -m workflows.infrastructure.boundary.runtime``。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from ...support.translations import tr


def _ensure_src_path() -> None:
    here = Path(__file__).resolve()
    src = here.parents[3]
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))


def _restore_base_mask(workdir: Path, log) -> None:
    from workflows.infrastructure.boundary.rect_boundary import restore_base_mask_nml

    restore_base_mask_nml(workdir)
    log("BOUNDARY: restored original MASK%FILENAME/IDLA")


def main(argv: list[str] | None = None) -> int:
    _ensure_src_path()
    parser = argparse.ArgumentParser(prog="python -m workflows.infrastructure.boundary.runtime")
    parser.add_argument("--workdir", required=True, help="算例工作目录")
    parser.add_argument(
        "--phase",
        choices=["lock", "pregrid", "postgrid", "all", "unlock"],
        default="all",
        help="lock: 仅获取作业锁；pregrid: 残留检查与谱准备；postgrid: ww3_bounc 与发布；unlock: 释放运行锁",
    )
    parser.add_argument(
        "--execution-context",
        choices=["local", "compute"],
        default="local",
        help="local：笔记本/本机；compute：计算节点（远程谱按本机 POSIX 路径读取，可执行文件用服务器 ST 映射）",
    )
    parser.add_argument("--lock-owner", default=None, help="跨阶段共用的作业锁标识（UUID），禁止用裸 PID")
    args = parser.parse_args(argv)

    workdir = Path(args.workdir).expanduser().resolve()
    params = workdir / "params.yml"
    if not params.is_file():
        print(f"BOUNDARY: missing params.yml in {workdir}", file=sys.stderr)
        return 2

    def log(message: str) -> None:
        print(message, flush=True)

    from workflows.application.boundary_preparation import bind_execution_workdir, prepare_boundary_inputs, run_ww3_bounc, verify_boundary_runtime
    from workflows.application.configuration import load_pipeline_config
    from workflows.infrastructure.boundary.errors import BoundaryError
    from workflows.infrastructure.boundary.manifest import WorkdirLock, archive_managed_nest, inspect_unmanaged_nest

    owner = str(args.lock_owner).strip() if args.lock_owner else None
    lock = WorkdirLock(workdir, owner=owner)
    keep_lock = owner is not None and args.phase not in {"unlock", "all"}
    if args.phase == "unlock":
        lock.release()
        log("BOUNDARY: lock released")
        return 0

    try:
        lock.acquire()
        if args.phase == "lock":
            log("BOUNDARY: lock acquired")
            return 0
        config = bind_execution_workdir(load_pipeline_config(params, validation_stage="boundary"), workdir)
        exec_ctx = str(args.execution_context or "local")
        if not config.boundary.enabled:
            log("BOUNDARY: mode=none")
            inspect_unmanaged_nest(workdir)
            archived = archive_managed_nest(workdir)
            _restore_base_mask(workdir, log)
            if archived:
                log(f"BOUNDARY: archived managed nest.ww3 -> {archived}")
            return 0
        loc = str(config.boundary.source.location or "local").lower()
        if exec_ctx == "local" and loc == "remote":
            raise BoundaryError(
                "BOUNDARY_LOCATION_MISMATCH",
                tr("boundary_local_run_remote_source", "本地运行不能引用远程谱来源，首版不自动下载原始谱"),
                hints=[tr("boundary_hint_use_server_or_local", "使用服务器执行，或把 source.location 改为 local")],
            )
        if str(config.grid.grid_type or "").lower() == "nested":
            raise BoundaryError(
                "BOUNDARY_GRID_UNSUPPORTED",
                tr("boundary_nested_unsupported", "首版不支持嵌套多网格外部谱"),
                context={"grid_type": config.grid.grid_type},
            )
        if args.phase in {"pregrid", "all"}:
            result = prepare_boundary_inputs(config, execution_context=exec_ctx, log=log, lock=lock)
            log(f"BOUNDARY: prepare state={result.state}")
        if args.phase in {"postgrid", "all"}:
            if args.phase == "all" and not (workdir / "mod_def.ww3").is_file():
                log(tr("boundary_log_skip_postgrid", "BOUNDARY: skip postgrid（尚无 mod_def.ww3）"))
                return 0
            run_ww3_bounc(config, execution_context=exec_ctx, log=log)
            verify_boundary_runtime(config, log=log)
        return 0
    except BoundaryError as exc:
        print(json.dumps({"error": exc.to_dict()}, ensure_ascii=False), file=sys.stderr)
        print(f"BOUNDARY {exc.code}: {exc.message}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"BOUNDARY unexpected error: {exc}", file=sys.stderr)
        return 1
    finally:
        if args.phase == "unlock":
            pass
        elif keep_lock:
            lock.drop_local()
        else:
            lock.release()


if __name__ == "__main__":
    raise SystemExit(main())
