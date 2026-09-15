"""GUI/CLI 共用的外部边界谱编排。"""

from __future__ import annotations

import json
import shutil
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from ..domain.boundary_models import (
    BOUNDARY_SCHEMA_VERSION,
    SELECTION_ALGO_VERSION,
    BoundaryInspection,
    BoundaryIssue,
    BoundaryPlan,
    BoundaryResult,
    BoundaryStation,
    utc_now_iso,
)
from ..domain.config_models import PipelineConfig
from ..infrastructure.boundary.errors import BoundaryError
from ..infrastructure.boundary.executables import resolve_boundary_executables, selected_executable_dir
from ..infrastructure.boundary.manifest import (
    WorkdirLock,
    archive_managed_nest,
    atomic_replace,
    atomic_write_json,
    file_digest_record,
    fingerprint_payload,
    inspect_unmanaged_nest,
    load_manifest,
    record_managed_file,
    save_manifest,
    sha256_file,
)
from ..infrastructure.boundary.rect_boundary import (
    build_target_points,
    read_target_points_csv,
    restore_base_mask_nml,
    set_mask_nml,
    write_mask_idla1,
    write_target_points_csv,
)
from ..infrastructure.boundary.spectra_normalizer import (
    align_spectral_axes,
    assert_time_gaps,
    crop_halo_indices,
    crop_with_halo,
    efth_unit_scale,
    infer_direction_convention,
    merge_station_time_series,
    overlap_time_indices,
    sanitize_efth,
    times_identical,
    write_station_file,
)
from ..infrastructure.boundary.spectra_reader import (
    assign_source_ids,
    inspect_spectra_file,
    read_station_efth,
)
from ..infrastructure.boundary.spatial_mapping import involved_source_ids, map_targets, read_mapping_csv, write_mapping_csv
from ..infrastructure.boundary.spectrum_coords import parse_spectrum_from_nml, spectral_fingerprint
from ..infrastructure.boundary.time_window import effective_window, format_ww3_time
from ..infrastructure.boundary.ww3_bounc_nml import (
    compare_mapping_with_nest,
    memory_estimate_bytes,
    read_nest_file,
    sample_compare_nest_spectra,
    write_bounc_nml,
    write_read_nml,
    write_spec_list,
)
from ..support.logging import CoreLogger, LogCallback
from ..support.translations import tr


LogFn = Callable[[str], None]
CancelFn = Callable[[], None]


def _log(log: LogFn | CoreLogger | None, message: str) -> None:
    if log is None:
        return
    if hasattr(log, "log"):
        log.log(message)
        return
    log(message)


def _issue_from_error(exc: BoundaryError) -> BoundaryIssue:
    return BoundaryIssue(code=exc.code, message=exc.message, context=exc.context, hints=exc.hints)


def assert_grid_supported(config: PipelineConfig) -> None:
    if not config.boundary.enabled:
        return
    mesh = str(config.grid.mesh_type or "").lower()
    gtype = str(config.grid.grid_type or "").lower()
    if mesh != "structured" or gtype != "normal":
        raise BoundaryError(
            "BOUNDARY_GRID_UNSUPPORTED",
            tr("boundary_grid_single_level_only", "首版外部边界谱仅支持单层结构化经纬度矩形网格"),
            context={"mesh_type": mesh, "grid_type": gtype},
            hints=[tr("boundary_hint_structured_normal", "选择 mesh_type=structured 且 grid_type=normal")],
        )
    if gtype == "nested" or (config.grid.nested_levels and len(config.grid.nested_levels) > 1 and gtype == "nested"):
        raise BoundaryError(
            "BOUNDARY_GRID_UNSUPPORTED",
            tr("boundary_multi_unsupported", "外部谱驱动 ww3_multi 待支持"),
            context={"grid_type": gtype},
        )


def _source_files(config: PipelineConfig) -> list[str]:
    files = [str(item).strip() for item in (config.boundary.source.files or []) if str(item).strip()]
    if config.boundary.enabled and not files:
        raise BoundaryError(
            "BOUNDARY_SOURCE_MISSING",
            tr("boundary_source_files_required", "启用外部边界谱时 source.files 不能为空"),
        )
    loc = str(config.boundary.source.location or "local").lower()
    if loc not in {"local", "remote"}:
        raise BoundaryError("BOUNDARY_LOCATION_MISMATCH", tr("boundary_unknown_location", "未知 source.location：{loc}").format(loc=loc))
    fmt = str(config.boundary.source.format or "ww3_netcdf").lower()
    if fmt != "ww3_netcdf":
        if fmt in {"ascii", "nest", "nest.ww3", "binary"}:
            raise BoundaryError(
                "BOUNDARY_SOURCE_MISSING",
                tr("boundary_format_supported", "首版支持格式为 WW3 NetCDF 二维谱"),
                context={"format": fmt},
                hints=[tr("boundary_hint_use_ounp_netcdf", "使用 ww3_ounp 点谱 NetCDF，不要直接导入 nest.ww3 或 ASCII")],
            )
        raise BoundaryError("BOUNDARY_SOURCE_MISSING", tr("boundary_format_unsupported", "不支持的谱格式 {fmt}").format(fmt=fmt))
    return files


def inspect_boundary(
    config: PipelineConfig,
    *,
    execution_context: str = "local",
    depth: str = "metadata",
    log: LogFn | CoreLogger | None = None,
) -> BoundaryInspection:
    """depth=metadata|full。纯配置检查不得隐式 SSH。"""
    inspection = BoundaryInspection(
        validation_depth=depth,
        source_location=str(config.boundary.source.location or "local"),
        files=list(config.boundary.source.files or []),
    )
    if not config.boundary.enabled:
        inspection.state = "disabled"
        return inspection
    try:
        assert_grid_supported(config)
        files = _source_files(config)
        loc = str(config.boundary.source.location or "local").lower()
        if execution_context == "local" and loc == "remote":
            inspection.state = "deferred_remote"
            inspection.pending_checks = [
                "remote_metadata",
                "full_spectra",
                "time_coverage",
                "spatial_mapping",
            ]
            inspection.issues.append(
                BoundaryIssue(
                    code="BOUNDARY_LOCATION_MISMATCH",
                    message=tr("boundary_remote_config_only", "当前只检查了配置；服务器谱的数据检查尚未完成"),
                    hints=[tr("boundary_hint_submit_or_local", "提交计算节点检查，或把来源改为本地文件")],
                )
            )
            _log(log, tr("boundary_log_remote_config_only", "外部边界谱：服务器来源，本地仅完成配置检查（非全部通过）"))
            return inspection
        if loc == "remote" and depth == "metadata" and execution_context != "remote":
            inspection.state = "deferred_remote"
            inspection.pending_checks = ["remote_metadata", "full_spectra"]
            return inspection
        metas = []
        stations: list[BoundaryStation] = []
        for path in files:
            if loc == "local" and not Path(path).expanduser().is_file():
                raise BoundaryError("BOUNDARY_SOURCE_MISSING", tr("boundary_spectra_file_missing", "谱文件不存在：{path}").format(path=path), context={"path": path})
            _log(log, tr("boundary_log_inspect_file", "检查谱文件：{path}").format(path=path))
            meta = inspect_spectra_file(path)
            metas.append(meta)
            stations.extend(meta.stations)
        stations = assign_source_ids(stations)
        # merge same location
        merged: dict[tuple[str, float, float], BoundaryStation] = {}
        for station in stations:
            key = (station.name, round(station.lon, 6), round(station.lat, 6))
            if key in merged:
                for fp in station.file_paths:
                    if fp not in merged[key].file_paths:
                        merged[key].file_paths.append(fp)
            else:
                merged[key] = station
        stations = list(merged.values())
        inspection.stations = stations
        times = [t for meta in metas for t in meta.times]
        if times:
            inspection.time_start = min(times).strftime("%Y-%m-%dT%H:%M:%SZ")
            inspection.time_end = max(times).strftime("%Y-%m-%dT%H:%M:%SZ")
            inspection.n_times = len(sorted({t.isoformat() for t in times}))
        if metas:
            inspection.spectral = None
            inspection.artifacts["n_files"] = str(len(metas))
        inspection.state = "metadata_checked" if depth == "metadata" else "needs_inspection"
        inspection.pending_checks = []
        if depth == "metadata":
            inspection.pending_checks = ["full_spectra", "time_coverage", "missing_values"]
            _log(log, tr("boundary_log_header_checked", "外部边界谱：已完成文件头检查，完整有效值检查在准备阶段"))
        return inspection
    except BoundaryError as exc:
        inspection.state = "failed"
        inspection.issues.append(_issue_from_error(exc))
        _log(log, f"❌ {exc.message}")
        return inspection


def _workdir(config: PipelineConfig) -> Path:
    return Path(config.workdir.path)


def bind_execution_workdir(config: PipelineConfig, workdir: Path) -> PipelineConfig:
    """运行入口的 --workdir 覆盖配置中的本机绝对路径。"""
    config.workdir.path = Path(workdir).expanduser().resolve()
    return config


def _dependency_grid_fingerprint(workdir: Path, geo: dict, sides: list) -> str:
    from ..infrastructure.boundary.rect_boundary import read_mask_origin

    origin = read_mask_origin(workdir)
    if origin is None:
        named = str((geo or {}).get("mask_filename") or "")
        if Path(named).name == "grid.mask_boundary":
            named = "grid.mask_nobound" if (Path(workdir) / "grid.mask_nobound").is_file() else named
        origin = {
            "filename": named or "grid.mask_nobound",
            "idla": int((geo or {}).get("mask_idla") or 1),
            "idfm": int((geo or {}).get("mask_idfm") or 1),
        }
    mask_file = Path(workdir) / str(origin.get("filename") or "")
    if not mask_file.is_file():
        named = geo.get("mask_filename") if geo else None
        mask_file = Path(workdir) / str(named) if named else Path(workdir) / "grid.mask_nobound"
    return fingerprint_payload(
        {
            "geo": {k: geo[k] for k in ("nx", "ny", "sx", "sy", "x0", "y0") if geo and k in geo},
            "sides": list(sides),
            "mask": sha256_file(mask_file) if mask_file.is_file() else "",
            "mask_idla": origin.get("idla"),
            "algo": (geo or {}).get("selection_algo_version") or SELECTION_ALGO_VERSION,
        }
    )


def _source_path_key(path: str) -> str:
    return str(Path(path).expanduser()).replace("\\", "/")


def _same_source_files(plan_files: list[str], current_files: list[str]) -> bool:
    if not plan_files:
        return False
    return [_source_path_key(p) for p in plan_files] == [_source_path_key(p) for p in current_files]


def _normalized_reuse_valid(
    existing: BoundaryPlan | None,
    *,
    workdir: Path,
    start,
    end,
    method: str,
    max_km: float,
    max_gap: int,
    grid_fp: str,
    spec_fp: str,
    files: list[str],
) -> bool:
    if existing is None or not existing.normalized_relpaths:
        return False
    if not existing.grid_fingerprint or not existing.spectral_fingerprint:
        return False
    if not _same_source_files(existing.files, files):
        return False
    if existing.interpolation != method:
        return False
    if abs(float(existing.max_distance_km or 0) - float(max_km)) > 1e-9:
        return False
    if int(existing.max_time_gap_seconds or 0) != int(max_gap):
        return False
    if existing.effective_start != format_ww3_time(start):
        return False
    if existing.effective_end != format_ww3_time(end):
        return False
    if existing.grid_fingerprint != grid_fp:
        return False
    if existing.spectral_fingerprint != spec_fp:
        return False
    if not (workdir / "boundary" / "mapping.csv").is_file():
        return False
    if not (workdir / "boundary" / "normalized" / "spec.list").is_file():
        return False
    for rel in existing.normalized_relpaths:
        path = workdir / rel
        if not path.is_file():
            return False
        stored = (existing.normalized_digests or {}).get(rel) or (existing.normalized_digests or {}).get(Path(rel).name)
        if not stored or stored != sha256_file(path):
            return False
    return True


def _restore_reused_mask(workdir: Path, config: PipelineConfig, log: LogFn | CoreLogger | None) -> None:
    """复用谱包时仍必须写出活动掩码并改回 MASK%FILENAME。"""
    sides = config.boundary.selection.sides or ["west", "east", "south", "north"]
    targets, derived_mask, _geo = build_target_points(
        workdir, sides, inset_cells=int(config.boundary.selection.inset_cells or 1)
    )
    bdir = workdir / "boundary"
    write_mask_idla1(bdir / "grid.mask_boundary", derived_mask)
    write_target_points_csv(bdir / "target_points.csv", targets)
    set_mask_nml(workdir / "ww3_grid.nml", "boundary/grid.mask_boundary", idla=1, idfm=1)
    _log(log, tr("boundary_log_reuse_mask_restored", "复用谱包：已恢复活动掩码，边界点 {n_targets}").format(n_targets=len(targets)))


def build_boundary_plan(
    config: PipelineConfig,
    *,
    inspection: BoundaryInspection | None = None,
    effective_start: datetime | None = None,
    effective_end: datetime | None = None,
    log: LogFn | CoreLogger | None = None,
    remote: bool = False,
) -> BoundaryPlan:
    if not config.boundary.enabled:
        return BoundaryPlan(state="disabled")
    assert_grid_supported(config)
    workdir = _workdir(config)
    if effective_start is None or effective_end is None:
        effective_start, effective_end, _init = effective_window(config, workdir=workdir)
    loc = str(config.boundary.source.location or "local").lower()
    exec_mode = "remote_source" if loc == "remote" else "normalized_bundle"
    if loc == "remote" and not remote:
        exec_mode = "remote_source"
    plan = BoundaryPlan(
        state="needs_inspection",
        execution_inputs_mode=exec_mode,
        effective_start=format_ww3_time(effective_start),
        effective_end=format_ww3_time(effective_end),
        interpolation=str(config.boundary.interpolation.method or "nearest"),
        max_distance_km=config.boundary.interpolation.max_distance_km,
        max_time_gap_seconds=config.boundary.validation.max_time_gap_seconds,
        files=list(config.boundary.source.files or []),
    )
    if loc == "remote" and not remote:
        plan.state = "deferred_remote"
        plan.execution_inputs_mode = "remote_source"
        plan.executable_dir = selected_executable_dir(config, remote=True)
        plan.pending_checks = ["remote_full_spectra", "ww3_bounc_on_compute_node"]
        _log(log, tr("boundary_log_remote_plan", "服务器来源：已生成可执行计划，数据准备尚未完成"))
        return plan
    try:
        tools = resolve_boundary_executables(config, remote=remote)
        plan.executable_dir = tools["directory"]
        plan.ww3_bounc = tools["ww3_bounc"]
        plan.ww3_grid = tools["ww3_grid"]
    except BoundaryError as exc:
        plan.state = "failed"
        plan.notes.append(exc.message)
        raise
    plan.state = "metadata_checked"
    return plan


def prepare_boundary_inputs(
    config: PipelineConfig,
    *,
    plan: BoundaryPlan | None = None,
    execution_context: str = "local",
    log: LogFn | CoreLogger | None = None,
    cancel: CancelFn | None = None,
    lock: WorkdirLock | None = None,
    lock_owner: str | None = None,
) -> BoundaryResult:
    workdir = _workdir(config)
    started = utc_now_iso()
    token = str(lock_owner).strip() if lock_owner else None
    if lock is not None:
        return _prepare_entry(
            config,
            plan=plan,
            log=log,
            cancel=cancel,
            started=started,
            execution_context=execution_context,
        )
    with WorkdirLock(workdir, owner=token):
        return _prepare_entry(
            config,
            plan=plan,
            log=log,
            cancel=cancel,
            started=started,
            execution_context=execution_context,
        )


def _prepare_entry(
    config: PipelineConfig,
    *,
    plan: BoundaryPlan | None,
    log: LogFn | CoreLogger | None,
    cancel: CancelFn | None,
    started: str,
    execution_context: str,
) -> BoundaryResult:
    workdir = _workdir(config)
    if not config.boundary.enabled:
        inspect_unmanaged_nest(workdir)
        archived = archive_managed_nest(workdir)
        restore_base_mask_nml(workdir)
        return BoundaryResult(
            stage="normalize",
            state="disabled",
            ok=True,
            outputs={"archived_nest": archived or ""},
            started_at=started,
            finished_at=utc_now_iso(),
        )
    loc = str(config.boundary.source.location or "local").lower()
    if execution_context == "local" and loc == "remote":
        plan = build_boundary_plan(config, log=log, remote=False)
        bdir = workdir / "boundary"
        bdir.mkdir(parents=True, exist_ok=True)
        atomic_write_json(bdir / "plan.json", plan.to_dict())
        _log(log, tr("boundary_log_remote_plan_deferred", "服务器来源：已生成可执行计划，数据准备尚未完成（deferred_remote）"))
        return BoundaryResult(
            stage="normalize",
            state="deferred_remote",
            ok=True,
            outputs={"plan": str(bdir / "plan.json")},
            started_at=started,
            finished_at=utc_now_iso(),
            pending_checks=list(plan.pending_checks),
        )
    if execution_context not in {"local", "compute"}:
        raise BoundaryError("BOUNDARY_LOCATION_MISMATCH", tr("boundary_unknown_execution_context", "未知 execution_context：{execution_context}").format(execution_context=execution_context))
    return _prepare_locked(
        config,
        plan=plan,
        log=log,
        cancel=cancel,
        started=started,
        execution_context=execution_context,
    )


def _prepare_locked(
    config: PipelineConfig,
    *,
    plan: BoundaryPlan | None,
    log: LogFn | CoreLogger | None,
    cancel: CancelFn | None,
    started: str,
    execution_context: str = "local",
) -> BoundaryResult:
    workdir = _workdir(config)
    bdir = workdir / "boundary"
    bdir.mkdir(parents=True, exist_ok=True)
    inspect_unmanaged_nest(workdir)
    start, end, init_mode = effective_window(config, workdir=workdir)
    _log(log, tr("boundary_log_window", "有效积分窗口 {start} → {end}（{init_mode}）").format(start=format_ww3_time(start), end=format_ww3_time(end), init_mode=init_mode))
    files = _source_files(config)
    method = str(config.boundary.interpolation.method or "nearest")
    max_km = config.boundary.interpolation.max_distance_km
    max_gap = config.boundary.validation.max_time_gap_seconds
    if max_km is None or float(max_km) <= 0:
        raise BoundaryError("BOUNDARY_SPATIAL_COVERAGE", tr("boundary_interp_max_distance_required", "必须填写正的 interpolation.max_distance_km"))
    if max_gap is None or int(max_gap) <= 0:
        raise BoundaryError("BOUNDARY_TIME_GAP", tr("boundary_validation_max_gap_required", "必须填写正的 validation.max_time_gap_seconds"))
    memory_limit = int(config.boundary.resources.memory_limit_mb or 1024) * 1024 * 1024
    sides = config.boundary.selection.sides or ["west", "east", "south", "north"]
    loc = str(config.boundary.source.location or "local").lower()
    files_ok = all(Path(p).expanduser().is_file() for p in files)
    existing = plan or load_plan(workdir)
    geo_preview = None
    try:
        from ..infrastructure.boundary.rect_boundary import load_rect_geometry

        geo_preview = load_rect_geometry(workdir)
    except BoundaryError:
        geo_preview = {}
    target_spec = parse_spectrum_from_nml(workdir / "ww3_grid.nml", config.ww3_grid.parameters)
    grid_fp = _dependency_grid_fingerprint(workdir, geo_preview, sides)
    spec_fp = spectral_fingerprint(target_spec)
    if loc == "local" and not files_ok:
        if _normalized_reuse_valid(
            existing,
            workdir=workdir,
            start=start,
            end=end,
            method=method,
            max_km=float(max_km),
            max_gap=int(max_gap),
            grid_fp=grid_fp,
            spec_fp=spec_fp,
            files=files,
        ):
            _restore_reused_mask(workdir, config, log)
            _log(log, tr("boundary_log_reuse_package", "复用已有规范化谱包（源文件不在本机，时间/网格/谱离散/来源/指纹一致）"))
            return BoundaryResult(
                stage="normalize",
                state="prepared",
                ok=True,
                outputs={"plan": str(bdir / "plan.json"), "normalized": str(bdir / "normalized")},
                started_at=started,
                finished_at=utc_now_iso(),
                pending_checks=list(existing.pending_checks),
            )
        raise BoundaryError(
            "BOUNDARY_STALE" if existing and existing.normalized_relpaths else "BOUNDARY_SOURCE_MISSING",
            tr("boundary_stale_package", "找不到源谱文件，且已有规范化谱包与当前时间窗、网格、谱离散或源指纹不一致"),
            context={
                "files": files[:3],
                "requested_end": format_ww3_time(end),
                "plan_end": getattr(existing, "effective_end", None),
                "grid_fingerprint": grid_fp,
                "spectral_fingerprint": spec_fp,
            },
            hints=[tr("boundary_hint_reprepare_with_sources", "在有源文件的机器上重新 prepare-boundary，再上传规范化包")],
        )

    # 目标点与派生掩码
    targets, derived_mask, geo = build_target_points(
        workdir, sides, inset_cells=int(config.boundary.selection.inset_cells or 1)
    )
    nobound = workdir / "grid.mask_nobound"
    base = Path(geo["base_mask_path"])
    if base.is_file() and not nobound.is_file() and base.resolve() != nobound.resolve():
        shutil.copy2(base, nobound)
    mask_path = bdir / "grid.mask_boundary"
    write_mask_idla1(mask_path, derived_mask)
    write_target_points_csv(bdir / "target_points.csv", targets)
    set_mask_nml(workdir / "ww3_grid.nml", "boundary/grid.mask_boundary", idla=1, idfm=1)
    for side in geo.get("empty_sides") or []:
        _log(log, tr("boundary_log_side_no_wet", "该边无有效海点：{side}").format(side=side))
    _log(log, tr("boundary_log_active_points", "活动边界点数 {n_targets}（向内一格，算法 {algo}）").format(n_targets=len(targets), algo=geo.get('selection_algo_version')))
    grid_fp = _dependency_grid_fingerprint(workdir, geo, sides)

    # 源索引：先用元数据映射，再只读取参与站点
    station_slices: dict[str, list] = defaultdict(list)
    station_meta: dict[str, BoundaryStation] = {}
    source_index = {"files": [], "stations": []}
    file_records: list[tuple] = []
    for path in files:
        if cancel:
            cancel()
        meta = inspect_spectra_file(path)
        convention = infer_direction_convention(meta)
        scale, _unit = efth_unit_scale(meta.efth_units)
        source_index["files"].append(
            {
                "path": path,
                "n_stations": meta.n_stations,
                "time_start": meta.time_start,
                "time_end": meta.time_end,
                "layout": meta.layout,
            }
        )
        for idx, station in enumerate(meta.stations):
            file_records.append((path, idx, station, convention, scale, list(meta.times)))
    assigned = assign_source_ids([rec[2] for rec in file_records]) if file_records else []
    unique_stations: list[BoundaryStation] = []
    seen_ids: set[str] = set()
    for station in assigned:
        if station.source_id in seen_ids:
            continue
        seen_ids.add(station.source_id)
        unique_stations.append(station)
        station_meta[station.source_id] = station
    mappings = map_targets(targets, unique_stations, method=method, max_distance_km=float(max_km))
    write_mapping_csv(bdir / "mapping.csv", mappings)
    used_ids = involved_source_ids(mappings)
    n_freq = len(target_spec.frequencies_hz)
    n_dir = len(target_spec.directions_deg)
    times_by_id: dict[str, list] = defaultdict(list)
    for rec, station in zip(file_records, assigned):
        if station.source_id not in used_ids:
            continue
        times_by_id[station.source_id].extend(rec[5])
    n_time_est = 0
    needed_span: dict[str, tuple] = {}
    for source_id in used_ids:
        stamps = []
        seen = set()
        for raw in times_by_id.get(source_id) or []:
            t = raw.astimezone(timezone.utc) if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
            t = t.replace(microsecond=0)
            if t in seen:
                continue
            seen.add(t)
            stamps.append(t)
        stamps.sort()
        i0, i1 = crop_halo_indices(stamps, start, end)
        n_time_est = max(n_time_est, i1 - i0)
        needed_span[source_id] = (stamps[i0], stamps[i1 - 1])
    mem = memory_estimate_bytes(len(used_ids), n_time_est, n_freq, n_dir)
    if mem > memory_limit:
        raise BoundaryError(
            "BOUNDARY_MEMORY_BUDGET",
            tr("boundary_memory_budget_exceeded", "转换估计 {need_mib:.0f} MiB 超过预算 {limit_mib:.0f} MiB").format(need_mib=mem / 1024 / 1024, limit_mib=memory_limit / 1024 / 1024),
            context={"estimate_bytes": mem, "limit_bytes": memory_limit},
            hints=[tr("boundary_hint_memory", "缩短时段、减少源站点或提高 resources.memory_limit_mb")],
        )

    for rec, station in zip(file_records, assigned):
        if station.source_id not in used_ids:
            continue
        if cancel:
            cancel()
        path, idx, _station, convention, scale, times_meta = rec
        span = needed_span[station.source_id]
        i0, i1 = overlap_time_indices(times_meta, span[0], span[1])
        if i1 <= i0:
            continue
        times, freqs, dirs, efth = read_station_efth(path, idx, time_slice=slice(i0, i1))
        aligned = align_spectral_axes(
            freqs,
            dirs,
            efth,
            target_spec,
            convention=convention,
            unit_scale=scale,
        )
        aligned, n_clip, max_fix = sanitize_efth(aligned)
        if n_clip:
            _log(log, tr("boundary_log_negative_clipped", "站点 {station} 将 {n_clip} 个舍入负值截为零，最大修正 {max_fix}").format(station=station.name, n_clip=n_clip, max_fix=max_fix))
        station_slices[station.source_id].append((list(times), aligned, station, path))
        station_meta[station.source_id] = station

    merged_series = {}
    time_sets = []
    for source_id in used_ids:
        chunks = station_slices.get(source_id) or []
        merged_t, merged_e = merge_station_time_series([(t, e) for t, e, _s, _p in chunks])
        merged_t, merged_e = crop_with_halo(merged_t, merged_e, start, end)
        assert_time_gaps(merged_t, int(max_gap))
        merged_series[source_id] = (merged_t, merged_e, station_meta[source_id])
        time_sets.append(merged_t)
    if not times_identical(time_sets):
        raise BoundaryError(
            "BOUNDARY_TIME_COVERAGE",
            tr("boundary_station_times_differ", "参与站点的时间坐标必须逐项一致，不能只比较步数"),
        )

    norm_dir = bdir / "normalized"
    if norm_dir.exists():
        shutil.rmtree(norm_dir)
    norm_dir.mkdir(parents=True)
    relpaths = []
    for source_id in used_ids:
        if cancel:
            cancel()
        times, efth, station = merged_series[source_id]
        out_name = f"{source_id}.nc"
        out_path = norm_dir / out_name
        write_station_file(
            out_path,
            name=station.name,
            lon=station.lon,
            lat=station.lat,
            times=times,
            frequencies=target_spec.frequencies_hz,
            directions=target_spec.directions_deg,
            efth=efth,
        )
        relpaths.append(f"boundary/normalized/{out_name}")
        # variance check vs last raw is already aligned
    write_spec_list(norm_dir / "spec.list", [Path(p).name for p in relpaths])
    normalized_digests = {rel: sha256_file(workdir / rel) for rel in relpaths}

    source_fp = fingerprint_payload(
        {
            "files": [file_digest_record(Path(p)) if Path(p).is_file() else {"path": p} for p in files],
            "stations": used_ids,
        }
    )
    plan_out = BoundaryPlan(
        state="prepared",
        execution_inputs_mode="normalized_bundle" if str(config.boundary.source.location).lower() == "local" else "remote_source",
        effective_start=format_ww3_time(start),
        effective_end=format_ww3_time(end),
        interpolation=method,
        max_distance_km=float(max_km),
        max_time_gap_seconds=int(max_gap),
        grid_fingerprint=grid_fp,
        spectral_fingerprint=spec_fp,
        source_fingerprint=source_fp,
        files=list(files),
        normalized_relpaths=relpaths,
        normalized_digests=normalized_digests,
        target_count=len(targets),
        mapped_count=len(mappings),
        memory_estimate_bytes=mem,
        normalized_size_bytes=sum((norm_dir / Path(p).name).stat().st_size for p in relpaths),
        artifacts={
            "target_points": "boundary/target_points.csv",
            "mapping": "boundary/mapping.csv",
            "mask": "boundary/grid.mask_boundary",
            "spec_list": "boundary/normalized/spec.list",
            "source_index": "boundary/source_index.json",
        },
        notes=[f"init={init_mode}"],
    )
    try:
        tools = resolve_boundary_executables(config, remote=execution_context == "compute")
        plan_out.executable_dir = tools["directory"]
        plan_out.ww3_bounc = tools["ww3_bounc"]
        plan_out.ww3_grid = tools["ww3_grid"]
    except BoundaryError as exc:
        plan_out.executable_dir = selected_executable_dir(config, remote=execution_context == "compute")
        plan_out.pending_checks.append("ww3_bounc_at_runtime")
        plan_out.notes.append(exc.message)

    atomic_write_json(bdir / "plan.json", plan_out.to_dict())
    atomic_write_json(bdir / "source_index.json", source_index)
    atomic_write_json(
        bdir / "inspection.json",
        {
            "schema_version": BOUNDARY_SCHEMA_VERSION,
            "state": plan_out.state,
            "validation_depth": "full",
            "stations": [
                {"id": s.source_id, "name": s.name, "lon": s.lon, "lat": s.lat}
                for s in unique_stations
                if s.source_id in used_ids
            ],
            "spectral": {
                "frequencies_hz": target_spec.frequencies_hz,
                "directions_deg": target_spec.directions_deg,
                "thoff": target_spec.thoff,
            },
        },
    )
    _log(log, tr("boundary_log_normalized_ready", "已准备规范化谱 {n_files} 个站点文件").format(n_files=len(relpaths)))
    return BoundaryResult(
        stage="normalize",
        state=plan_out.state,
        ok=True,
        outputs={"plan": str(bdir / "plan.json"), "normalized": str(norm_dir)},
        started_at=started,
        finished_at=utc_now_iso(),
        pending_checks=list(plan_out.pending_checks),
    )


def load_plan(workdir: Path) -> BoundaryPlan | None:
    path = Path(workdir) / "boundary" / "plan.json"
    if not path.is_file():
        return None
    return BoundaryPlan.from_dict(json.loads(path.read_text(encoding="utf-8")))


def boundary_status(config: PipelineConfig, *, remote: bool = False) -> dict:
    workdir = _workdir(config)
    plan = load_plan(workdir)
    state = "disabled" if not config.boundary.enabled else "needs_input"
    pending = []
    if not config.boundary.enabled:
        return {"state": "disabled", "validation_depth": "none", "pending_checks": [], "artifacts": {}}
    if plan is None:
        return {
            "state": "needs_inspection",
            "validation_depth": "none",
            "pending_checks": ["inspect"],
            "artifacts": {},
        }
    # stale?
    try:
        current = build_boundary_plan(config, remote=remote)
        stale = False
        if plan.spectral_fingerprint and current.effective_start:
            if plan.effective_start != current.effective_start or plan.effective_end != current.effective_end:
                stale = True
        if plan.interpolation != str(config.boundary.interpolation.method or "nearest"):
            stale = True
        if plan.files and not _same_source_files(plan.files, list(config.boundary.source.files or [])):
            stale = True
        if stale:
            return {
                "state": "stale",
                "validation_depth": "plan",
                "pending_checks": ["reprepare"],
                "artifacts": plan.artifacts,
            }
    except BoundaryError as exc:
        return {
            "state": "failed",
            "validation_depth": "plan",
            "pending_checks": [],
            "artifacts": plan.artifacts,
            "error": exc.to_dict(),
        }
    return {
        "state": plan.state,
        "validation_depth": "full" if plan.state == "prepared" else "metadata",
        "pending_checks": list(plan.pending_checks),
        "artifacts": plan.artifacts,
        "target_count": plan.target_count,
        "mapped_count": plan.mapped_count,
    }


def verify_boundary_runtime(
    config: PipelineConfig,
    *,
    plan: BoundaryPlan | None = None,
    runtime_files: dict | None = None,
    log: LogFn | CoreLogger | None = None,
) -> BoundaryResult:
    workdir = _workdir(config)
    nest = Path((runtime_files or {}).get("nest") or (workdir / "nest.ww3"))
    started = utc_now_iso()
    if not nest.is_file():
        raise BoundaryError("BOUNDARY_VERIFY_FAILED", tr("boundary_nest_missing", "缺少 nest.ww3"))
    info = read_nest_file(nest)
    plan = plan or load_plan(workdir)
    if plan and info.nbi != plan.target_count:
        raise BoundaryError(
            "BOUNDARY_VERIFY_FAILED",
            tr("boundary_point_count_vs_plan", "边界点数与计划不一致：文件 {nbi}，计划 {planned}").format(nbi=info.nbi, planned=plan.target_count),
        )
    if plan:
        start = plan.effective_start
        end = plan.effective_end
        if info.times and start and info.times[0] > start:
            raise BoundaryError(
                "BOUNDARY_VERIFY_FAILED",
                tr("boundary_nest_start_uncovered", "边界文件时间未覆盖有效起点"),
                context={"first": info.times[0], "start": start},
            )
        if info.times and end and info.times[-1] < end:
            raise BoundaryError(
                "BOUNDARY_VERIFY_FAILED",
                tr("boundary_nest_end_uncovered", "边界文件时间未覆盖有效终点"),
                context={"last": info.times[-1], "end": end},
            )
    _log(log, tr("boundary_log_nest_readable", "nest.ww3 可读：NBI={nbi} NK={nk} NTH={nth} 时刻数={n_times} ({layout})").format(nbi=info.nbi, nk=info.nk, nth=info.nth, n_times=info.n_records, layout=info.layout))
    if plan:
        mapping_path = workdir / "boundary" / "mapping.csv"
        target_path = workdir / "boundary" / "target_points.csv"
        mappings = read_mapping_csv(mapping_path)
        targets = read_target_points_csv(target_path)
        source_index = {
            Path(rel).stem: i + 1 for i, rel in enumerate(plan.normalized_relpaths or [])
        }
        method = str(plan.interpolation or "nearest").lower()
        if not mappings or not targets or not source_index:
            raise BoundaryError(
                "BOUNDARY_VERIFY_FAILED",
                tr("boundary_verify_inputs_missing", "验收缺少 mapping.csv、目标点或规范化谱索引，无法与 nest 核对坐标和来源"),
            )
        compare_mapping_with_nest(
            mappings,
            targets,
            info,
            method=method,
            source_index=source_index,
        )
        sample_compare_nest_spectra(info, workdir, plan)
        _log(log, tr("boundary_log_mapping_verified", "{method} 映射记录 {n_rows} 条，已核对坐标、来源索引与谱值抽样").format(method=method, n_rows=len(info.mapping_indices)))
    return BoundaryResult(
        stage="verify_boundary",
        state="prepared",
        ok=True,
        outputs={"nest": str(nest)},
        diagnostics={"ident": info.ident, "layout": info.layout, "n_times": str(info.n_records)},
        started_at=started,
        finished_at=utc_now_iso(),
        exit_code=0,
    )


def run_ww3_bounc(
    config: PipelineConfig,
    *,
    run_id: str | None = None,
    execution_context: str = "local",
    log: LogFn | CoreLogger | None = None,
) -> BoundaryResult:
    """在隔离目录运行 ww3_bounc 并原子发布 nest.ww3。"""
    import subprocess

    workdir = _workdir(config)
    plan = load_plan(workdir)
    if plan is None or plan.state not in {"prepared", "deferred_remote"}:
        raise BoundaryError("BOUNDARY_STALE", tr("boundary_prepare_first", "请先准备边界输入"))
    tools = resolve_boundary_executables(config, remote=execution_context == "compute")
    run_id = run_id or uuid.uuid4().hex[:12]
    runtime = workdir / "boundary" / "runtime" / run_id
    if runtime.exists():
        shutil.rmtree(runtime)
    runtime.mkdir(parents=True)
    mod_def = workdir / "mod_def.ww3"
    if not mod_def.is_file():
        raise BoundaryError("BOUNDARY_BUILD_FAILED", tr("boundary_mod_def_missing", "缺少 ww3_grid 生成的 mod_def.ww3"))
    shutil.copy2(mod_def, runtime / "mod_def.ww3")
    for rel in plan.normalized_relpaths:
        src = workdir / rel
        shutil.copy2(src, runtime / src.name)
    write_spec_list(runtime / "spec.list", [Path(p).name for p in plan.normalized_relpaths])
    write_bounc_nml(runtime / "ww3_bounc.nml", spec_list="spec.list", method=plan.interpolation)
    _log(log, tr("boundary_log_run_bounc", "运行 {exe} （INTERP={interp}）").format(exe=tools['ww3_bounc'], interp='2' if plan.interpolation == 'linear' else '1'))
    proc = subprocess.run(
        [tools["ww3_bounc"]],
        cwd=str(runtime),
        capture_output=True,
        text=True,
    )
    (runtime / "boundary_build.log").write_text((proc.stdout or "") + (proc.stderr or ""), encoding="utf-8")
    if proc.returncode != 0 or not (runtime / "nest.ww3").is_file():
        raise BoundaryError(
            "BOUNDARY_BUILD_FAILED",
            tr("boundary_bounc_failed", "ww3_bounc 失败，退出码 {code}").format(code=proc.returncode),
            context={"log": str(runtime / "boundary_build.log"), "exit_code": proc.returncode},
        )
    try:
        result = verify_boundary_runtime(
            config, plan=plan, runtime_files={"nest": str(runtime / "nest.ww3")}, log=log
        )
    except BoundaryError:
        raise
    # optional READ mode
    write_read_nml(runtime / "ww3_bounc_read.nml")
    dest = workdir / "nest.ww3"
    atomic_replace(runtime / "nest.ww3", dest)
    digest = sha256_file(dest)
    manifest = load_manifest(workdir)
    record_managed_file(manifest, relpath="nest.ww3", kind="nest.ww3", sha256=digest, run_id=run_id)
    save_manifest(workdir, manifest)
    status = {
        "run_id": run_id,
        "stage": "build_boundary",
        "exit_code": 0,
        "nest_sha256": digest,
        "ww3_bounc": tools["ww3_bounc"],
        "mod_def_sha256": sha256_file(mod_def),
    }
    atomic_write_json(runtime / "status.json", status)
    _log(log, tr("boundary_log_published", "已发布 nest.ww3 （run_id={run_id}）").format(run_id=run_id))
    result.outputs["nest"] = str(dest)
    result.outputs["runtime"] = str(runtime)
    return result
