"""外部边界谱：配置关闭、几何、掩码与映射。"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest

from workflows.application.configuration import parse_pipeline_config
from workflows.domain.config_models import BoundaryConfig
from workflows.infrastructure.boundary.errors import BoundaryError
from workflows.infrastructure.boundary.geo import haversine_km
from workflows.infrastructure.boundary.manifest import inspect_unmanaged_nest
from workflows.infrastructure.boundary.rect_boundary import ring_indices, set_mask_nml, write_mask_idla1, is_wet
from workflows.infrastructure.boundary.spatial_mapping import map_targets
from workflows.infrastructure.boundary.spectra_normalizer import align_spectral_axes, efth_unit_scale, merge_station_time_series
from workflows.domain.boundary_models import BoundaryStation, BoundaryTargetPoint
from workflows.infrastructure.boundary.spectrum_coords import target_spectral_discrete


def _minimal_raw(**overrides):
    raw = {
        "workdir": {"path": "."},
        "forcing": {"wind": "wind.nc", "process_mode": "copy", "auto_associate": True},
        "grid": {
            "mesh_type": "structured",
            "grid_type": "normal",
            "gridgen_version": "Python",
            "lon": [110.0, 120.0],
            "lat": [20.0, 30.0],
            "structured": {
                "bathymetry": "GEBCO",
                "coastline_precision": "full",
                "min_dist": 20,
                "cut_off": 0,
                "lim_bathy": 0.4,
                "lim_val": 0.5,
                "split_lim": 0,
                "lake_tol": 50,
                "nested": {
                    "nested_contraction_coefficient": 1.3,
                    "levels": [{"dx": 0.5, "dy": 0.5, "lon": [110.0, 120.0], "lat": [20.0, 30.0]}],
                },
            },
            "smc": {
                "bathymetry": "ETOPO2",
                "bathy_convention": "elevation",
                "n_levels": 2,
                "wlevel": 0,
                "depmin": 0,
                "dshalw": -150,
                "generate_boundary_cells": True,
                "msea": 1,
            },
            "unstructured": {
                "hmax": 100,
                "hmin": 5,
                "hshr": 20,
                "nwav": 5,
                "dhdx": 0.2,
                "deep_ocean_threshold_m": 200,
                "margin_deg": 0.1,
                "edge_segments": 8,
            },
        },
        "calc": {"mode": "region"},
        "ww3": {
            "start_date": "20000101",
            "end_date": "20000102",
            "output_step": 3600,
            "st": "ST4",
            "output_scheme": {"standard": "HS DIR FP"},
        },
        "ww3_grid": {
            "SPECTRUM%XFR": 1.1,
            "SPECTRUM%FREQ1": 0.04,
            "SPECTRUM%NK": 8,
            "SPECTRUM%NTH": 12,
            "SPECTRUM%THOFF": 0,
            "TIMESTEPS%DTMAX": 3600,
            "TIMESTEPS%DTXY": 360,
            "TIMESTEPS%DTKTH": 360,
            "TIMESTEPS%DTMIN": 10,
        },
    }
    raw.update(overrides)
    return raw


def test_missing_boundary_is_disabled(tmp_path: Path):
    cfg = parse_pipeline_config(_minimal_raw(), base_dir=tmp_path, validation_stage="plot")
    assert cfg.boundary.mode == "none"
    assert cfg.boundary.enabled is False
    assert cfg.boundary.source.files == []


def test_is_wet_accepts_negative_elevation_after_sf():
    """DEPTH%SF=-1 后 bot 正水深变为负高程，仍是海点。"""
    assert is_wet(1, 4000.0)
    assert is_wet(1, -4000.0)
    assert is_wet(2, -10.0)
    assert not is_wet(1, 0.0)
    assert not is_wet(0, -4000.0)


def test_workdir_without_boundary_ignores_root_files(tmp_path: Path, monkeypatch):
    """工作目录缺少 boundary 段时必须关闭，即使根模板写了谱路径。"""
    import yaml

    from workflows.application.configuration import load_pipeline_config
    from workflows.infrastructure import runtime_config

    root_raw = _minimal_raw()
    root_raw["boundary"] = {
        "mode": "external_spectra",
        "source": {"format": "ww3_netcdf", "location": "local", "files": ["/root/secret.nc"]},
        "interpolation": {"max_distance_km": 50},
        "validation": {"max_time_gap_seconds": 10800},
    }
    root_path = tmp_path / "root_params.yml"
    root_path.write_text(yaml.safe_dump(root_raw, allow_unicode=True), encoding="utf-8")
    monkeypatch.setattr(runtime_config, "PARAMS_FILE", str(root_path))

    case = tmp_path / "case"
    case.mkdir()
    work_raw = _minimal_raw()
    work_raw["workdir"] = {"path": str(case)}
    (case / "params.yml").write_text(yaml.safe_dump(work_raw, allow_unicode=True), encoding="utf-8")
    cfg = load_pipeline_config(case / "params.yml", validation_stage="plot")
    assert cfg.boundary.enabled is False
    assert cfg.boundary.source.files == []


def test_workdir_without_key_stays_off(tmp_path: Path, monkeypatch):
    workdir_raw = _minimal_raw()
    cfg = parse_pipeline_config(workdir_raw, base_dir=tmp_path, validation_stage="plot")
    assert isinstance(cfg.boundary, BoundaryConfig)
    assert not cfg.boundary.enabled


def test_haversine_dateline_neighbors():
    d = haversine_km(179.5, 0.0, -179.5, 0.0)
    assert d < 200.0


def test_ring_indices_dedup_corners():
    cells = ring_indices(6, 6, ["west", "south"])
    assert (2, 2) in cells
    assert cells[(2, 2)] == {"west", "south"}
    assert (2, 5) in cells


def test_mask_idla1_roundtrip(tmp_path: Path):
    mask = np.array([[0, 1, 1], [1, 2, 1]], dtype=int)
    path = tmp_path / "grid.mask"
    write_mask_idla1(path, mask)
    text = path.read_text(encoding="utf-8")
    assert text.splitlines()[0] == "0 1 1"
    assert text.splitlines()[1] == "1 2 1"


def test_set_mask_nml_uncomments(tmp_path: Path):
    nml = tmp_path / "ww3_grid.nml"
    nml.write_text(
        "&MASK_NML\n"
        "! MASK%FILENAME = 'grid.mask'\n"
        "  MASK%IDLA       =  3\n"
        "/\n",
        encoding="utf-8",
    )
    set_mask_nml(nml, "boundary/grid.mask_boundary")
    text = nml.read_text(encoding="utf-8")
    assert "MASK%FILENAME" in text
    assert "boundary/grid.mask_boundary" in text
    assert "MASK%IDLA" in text and "=  1" in text
    assert "MASK%IDFM" in text


def test_nearest_tie_break_by_source_id():
    target = BoundaryTargetPoint(point_id="i0002j0002", i=2, j=2, lon=120.0, lat=30.0, sides=["west"])
    a = BoundaryStation(source_id="b", name="b", lon=120.0, lat=30.01)
    b = BoundaryStation(source_id="a", name="a", lon=120.0, lat=30.01)
    mapped = map_targets([target], [a, b], method="nearest", max_distance_km=50)
    assert mapped[0].source_ids[0] == "a"


def test_linear_out_of_segment_fails():
    target = BoundaryTargetPoint(point_id="i0002j0002", i=2, j=2, lon=130.0, lat=30.0, sides=["east"])
    s1 = BoundaryStation(source_id="s1", name="s1", lon=120.0, lat=30.0)
    s2 = BoundaryStation(source_id="s2", name="s2", lon=121.0, lat=30.0)
    with pytest.raises(BoundaryError) as exc:
        map_targets([target], [s1, s2], method="linear", max_distance_km=5000)
    assert exc.value.code == "BOUNDARY_SPATIAL_COVERAGE"


def test_unmanaged_nest_kept(tmp_path: Path):
    nest = tmp_path / "nest.ww3"
    nest.write_bytes(b"unknown-nest")
    with pytest.raises(BoundaryError) as exc:
        inspect_unmanaged_nest(tmp_path)
    assert exc.value.code == "BOUNDARY_UNMANAGED_FILE"
    assert nest.is_file()


def test_degree_units_scale():
    scale, unit = efth_unit_scale("m2 s degree-1")
    assert abs(scale - 180.0 / np.pi) < 1e-8
    assert "rad" in unit


def test_align_reverse_frequency_keeps_peak():
    spec = target_spectral_discrete(0.04, 1.1, 4, 8, 0.0)
    freqs = np.array(spec.frequencies_hz[::-1])
    dirs = np.array(spec.directions_deg)
    efth = np.zeros((2, 4, 8))
    efth[:, 0, 1] = 3.0  # 反序后的第一档对应目标最后一档
    aligned = align_spectral_axes(freqs, dirs, efth, spec, convention="to_direction", unit_scale=1.0)
    assert aligned.shape == (2, 4, 8)
    assert aligned[0, -1, 1] == 3.0


def test_assign_source_ids_stable_across_file_order():
    from workflows.infrastructure.boundary.spectra_reader import assign_source_ids
    from workflows.domain.boundary_models import BoundaryStation

    a1 = BoundaryStation("", "A", 120.0, 30.0, ["f1"])
    b1 = BoundaryStation("", "B", 121.0, 31.0, ["f1"])
    b2 = BoundaryStation("", "B", 121.0, 31.0, ["f2"])
    a2 = BoundaryStation("", "A", 120.0, 30.0, ["f2"])
    out = assign_source_ids([a1, b1, b2, a2])
    assert out[0].source_id == out[3].source_id == "src_000001"
    assert out[1].source_id == out[2].source_id == "src_000002"


def test_unknown_direction_convention():
    from workflows.infrastructure.boundary.spectra_normalizer import infer_direction_convention
    from workflows.infrastructure.boundary.spectra_reader import SpectraFileMeta

    meta = SpectraFileMeta(path="x.nc", dir_long_name="azimuth", dir_standard_name="", dir_units="degree")
    with pytest.raises(BoundaryError) as exc:
        infer_direction_convention(meta)
    assert exc.value.code == "BOUNDARY_CONVENTION_UNKNOWN"


def test_crop_halo_keeps_neighbors():
    from datetime import timedelta
    from workflows.infrastructure.boundary.spectra_normalizer import crop_with_halo

    times = [datetime(2000, 1, 1, tzinfo=timezone.utc) + timedelta(hours=h) for h in range(6)]
    efth = np.arange(6, dtype=float).reshape(6, 1, 1)
    start = datetime(2000, 1, 1, 1, 30, tzinfo=timezone.utc)
    end = datetime(2000, 1, 1, 3, 30, tzinfo=timezone.utc)
    cropped_t, cropped_e = crop_with_halo(times, efth, start, end)
    assert cropped_t[0].hour == 1
    assert cropped_t[-1].hour == 4


def test_skip_upload_runtime_and_nest():
    from workflows.infrastructure.remote.ssh_client import _skip_boundary_upload_dir, _skip_boundary_upload_file

    assert _skip_boundary_upload_dir("boundary/runtime/abc")
    assert not _skip_boundary_upload_dir("boundary/normalized")
    assert _skip_boundary_upload_file("nest.ww3")
    assert _skip_boundary_upload_file("mod_def.ww3")
    assert not _skip_boundary_upload_file("boundary/normalized/src_000001.nc")


def test_nest_mixed_header_nbi(tmp_path: Path):
    """ww3_bounc 把 NK/NTH/NBI 写在标识同一条 Fortran 记录里。"""
    import struct

    from workflows.infrastructure.boundary.ww3_bounc_nml import read_nest_file

    ident = b"WAVEWATCH III BOUNDARY DATA FILE"
    ver = b"III  1.03 "
    payload = ident + ver + struct.pack(">ii", 10, 24) + struct.pack(">fff", 1.1, 0.08, 3.0) + struct.pack(">i", 7)
    rec1 = struct.pack(">i", len(payload)) + payload + struct.pack(">i", len(payload))
    interp = bytes(7 * 40)
    rec2 = struct.pack(">i", len(interp)) + interp + struct.pack(">i", len(interp))
    timep = struct.pack(">iii", 20000101, 0, 7)
    rec3 = struct.pack(">i", 12) + timep + struct.pack(">i", 12)
    spec = bytes(960)
    rec4 = struct.pack(">i", 960) + spec + struct.pack(">i", 960)
    nest = tmp_path / "nest.ww3"
    nest.write_bytes(rec1 + rec2 + rec3 + rec4 * 7)
    info = read_nest_file(nest)
    assert info.nk == 10
    assert info.nth == 24
    assert info.nbi == 7
    assert info.n_records >= 1
    assert info.times[0] == "20000101 000000"


def test_merge_duplicate_same_ok_conflict_fails():
    t = datetime(2000, 1, 1, tzinfo=timezone.utc)
    frame = np.ones((2, 2))
    merged_t, merged_e = merge_station_time_series([([t], frame[None, ...]), ([t], frame[None, ...])])
    assert len(merged_t) == 1
    with pytest.raises(BoundaryError) as exc:
        merge_station_time_series([([t], frame[None, ...]), ([t], (frame * 2)[None, ...])])
    assert exc.value.code == "BOUNDARY_DUPLICATE_CONFLICT"


def test_ww3_ounp_direction_axis_nth24_thoff0():
    spec = target_spectral_discrete(0.08, 1.1, 10, 24, 0.0)
    native = [(450.0 - i * 15.0) % 360.0 for i in range(24)]
    assert spec.directions_deg[:3] == pytest.approx(native[:3])
    assert spec.directions_deg[0] == pytest.approx(90.0)


def test_linear_matches_ww3_bounc_planar_weights():
    target = BoundaryTargetPoint(point_id="target", i=2, j=2, lon=3.0, lat=60.0, sides=["west"])
    a = BoundaryStation(source_id="a", name="a", lon=0.0, lat=50.0)
    b = BoundaryStation(source_id="b", name="b", lon=8.0, lat=64.0)
    mapped = map_targets([target], [a, b], method="linear", max_distance_km=3000)[0]
    dx = b.lon - a.lon
    dy = b.lat - a.lat
    t = ((target.lon - a.lon) * dx + (target.lat - a.lat) * dy) / (dx * dx + dy * dy)
    w_by_id = dict(zip(mapped.source_ids, mapped.weights))
    assert w_by_id["a"] == pytest.approx(1.0 - t, abs=1e-6)
    assert w_by_id["b"] == pytest.approx(t, abs=1e-6)


def test_truncated_nest_missing_spectra_fails(tmp_path: Path):
    import struct

    from workflows.infrastructure.boundary.ww3_bounc_nml import read_nest_file

    ident = b"WAVEWATCH III BOUNDARY DATA FILE"
    ver = b"III  1.03 "
    payload = ident + ver + struct.pack(">ii", 10, 24) + struct.pack(">fff", 1.1, 0.08, 3.0) + struct.pack(">i", 7)
    rec1 = struct.pack(">i", len(payload)) + payload + struct.pack(">i", len(payload))
    interp = bytes(7 * 40)
    rec2 = struct.pack(">i", len(interp)) + interp + struct.pack(">i", len(interp))
    timep = struct.pack(">iii", 20000101, 0, 7)
    rec3 = struct.pack(">i", 12) + timep + struct.pack(">i", 12)
    nest = tmp_path / "nest.ww3"
    nest.write_bytes(rec1 + rec2 + rec3)
    with pytest.raises(BoundaryError) as exc:
        read_nest_file(nest)
    assert exc.value.code == "BOUNDARY_VERIFY_FAILED"


def test_idla3_reprepare_keeps_target_ids(tmp_path: Path):
    from workflows.infrastructure.boundary.rect_boundary import build_target_points, set_mask_nml, write_mask_idla1

    mask = np.ones((7, 7), dtype=int)
    mask[1, 1] = 0
    np.savetxt(tmp_path / "grid.mask_nobound", mask[::-1], fmt="%d")
    np.savetxt(tmp_path / "grid.bot", np.ones((7, 7)) * 1000, fmt="%d")
    (tmp_path / "ww3_grid.nml").write_text(
        "&RECT_NML\n RECT%NX=7\n RECT%NY=7\n RECT%SX=0.25\n RECT%SY=0.25\n RECT%X0=120\n RECT%Y0=10\n/\n"
        "&GRID_NML\n GRID%TYPE='RECT'\n GRID%CLOS='NONE'\n/\n"
        "&DEPTH_NML\n DEPTH%FILENAME='grid.bot'\n DEPTH%SF=-1\n DEPTH%IDLA=3\n/\n"
        "&MASK_NML\n MASK%FILENAME='grid.mask_nobound'\n MASK%IDLA=3\n MASK%IDFM=1\n/\n",
        encoding="utf-8",
    )
    p1, d1, _g1 = build_target_points(tmp_path, ["west"])
    write_mask_idla1(tmp_path / "boundary" / "grid.mask_boundary", d1)
    set_mask_nml(tmp_path / "ww3_grid.nml", "boundary/grid.mask_boundary")
    p2, _d2, _g2 = build_target_points(tmp_path, ["west"])
    assert [p.point_id for p in p1] == [p.point_id for p in p2]


def test_bind_execution_workdir_overrides_yaml_path(tmp_path: Path):
    from types import SimpleNamespace

    from workflows.application.boundary_preparation import bind_execution_workdir
    from workflows.domain.config_models import WorkdirConfig

    cfg = SimpleNamespace(workdir=WorkdirConfig(path=Path("/Users/someone/old")))
    bind_execution_workdir(cfg, tmp_path)
    assert cfg.workdir.path == tmp_path.resolve()


def test_spectrum_freq1_getter_exists():
    import ast
    from pathlib import Path as P

    module = ast.parse((P(__file__).resolve().parents[2] / "src/desktop/steps/ww3_panel.py").read_text())
    names = {n.name for n in ast.walk(module) if isinstance(n, ast.FunctionDef)}
    assert "spectrum_freq1_text" in names


def test_reuse_requires_time_grid_and_file_digests(tmp_path: Path):
    from datetime import timedelta

    from workflows.application.boundary_preparation import _normalized_reuse_valid
    from workflows.domain.boundary_models import BoundaryPlan
    from workflows.infrastructure.boundary.manifest import sha256_file
    from workflows.infrastructure.boundary.spectrum_coords import spectral_fingerprint
    from workflows.infrastructure.boundary.time_window import format_ww3_time

    spec = target_spectral_discrete(0.08, 1.1, 10, 24, 0.0)
    spec_fp = spectral_fingerprint(spec)
    start = datetime(2000, 1, 1, tzinfo=timezone.utc)
    end = datetime(2000, 1, 2, tzinfo=timezone.utc)
    rel = "boundary/normalized/src_000001.nc"
    nc = tmp_path / rel
    nc.parent.mkdir(parents=True)
    nc.write_bytes(b"normalized-packet")
    digest = sha256_file(nc)
    existing = BoundaryPlan(
        state="prepared",
        interpolation="nearest",
        max_distance_km=50.0,
        max_time_gap_seconds=10800,
        effective_start=format_ww3_time(start),
        effective_end=format_ww3_time(end),
        grid_fingerprint="grid-fp",
        spectral_fingerprint=spec_fp,
        files=["/data/src.nc"],
        normalized_relpaths=[rel],
        normalized_digests={rel: digest},
    )
    (tmp_path / "boundary" / "mapping.csv").write_text("target_id\n", encoding="utf-8")
    (tmp_path / "boundary" / "normalized" / "spec.list").write_text("src_000001.nc\n", encoding="utf-8")
    kwargs = dict(
        workdir=tmp_path,
        start=start,
        end=end,
        method="nearest",
        max_km=50.0,
        max_gap=10800,
        grid_fp="grid-fp",
        spec_fp=spec_fp,
        files=["/data/src.nc"],
    )
    assert _normalized_reuse_valid(existing, **kwargs)
    later = end + timedelta(hours=12)
    assert not _normalized_reuse_valid(existing, **{**kwargs, "end": later})
    assert not _normalized_reuse_valid(existing, **{**kwargs, "grid_fp": "other-grid"})
    assert not _normalized_reuse_valid(existing, **{**kwargs, "files": ["/other/missing.nc"]})
    existing.normalized_digests = {}
    assert not _normalized_reuse_valid(existing, **kwargs)


def test_fingerprint_check_does_not_write_mask_origin(tmp_path: Path):
    from workflows.application.boundary_preparation import _dependency_grid_fingerprint
    from workflows.infrastructure.boundary.rect_boundary import mask_origin_path

    geo = {
        "nx": 7,
        "ny": 7,
        "sx": 0.25,
        "sy": 0.25,
        "x0": 120.0,
        "y0": 10.0,
        "mask_filename": "boundary/grid.mask_boundary",
        "mask_idla": 1,
    }
    (tmp_path / "grid.mask_nobound").write_text("1 1\n", encoding="utf-8")
    _dependency_grid_fingerprint(tmp_path, geo, ["west"])
    assert not mask_origin_path(tmp_path).is_file()


def test_timesplit_files_cover_after_merge():
    from datetime import timedelta

    from workflows.infrastructure.boundary.spectra_normalizer import crop_halo_indices, overlap_time_indices

    start = datetime(2000, 1, 1, tzinfo=timezone.utc)
    end = datetime(2000, 1, 1, 12, tzinfo=timezone.utc)
    mid = datetime(2000, 1, 1, 6, tzinfo=timezone.utc)
    first = [start + timedelta(hours=h) for h in range(7)]
    second = [mid + timedelta(hours=h) for h in range(7)]
    with pytest.raises(BoundaryError) as exc:
        crop_halo_indices(first, start, end)
    assert exc.value.code == "BOUNDARY_TIME_COVERAGE"
    merged = sorted(set(first + second))
    i0, i1 = crop_halo_indices(merged, start, end)
    span0, span1 = merged[i0], merged[i1 - 1]
    a0, a1 = overlap_time_indices(first, span0, span1)
    b0, b1 = overlap_time_indices(second, span0, span1)
    assert a1 > a0 and b1 > b0
    assert (a1 - a0) + (b1 - b0) >= (i1 - i0)


def test_cross_node_lock_not_stolen_by_dead_pid(tmp_path: Path):
    from workflows.infrastructure.boundary.manifest import WorkdirLock

    first = WorkdirLock(tmp_path, owner="job-a", owner_pid=2147483000)
    first.acquire()
    first.drop_local()
    second = WorkdirLock(tmp_path)
    with pytest.raises(BoundaryError) as exc:
        second.acquire()
    assert exc.value.code == "BOUNDARY_WORKDIR_BUSY"
    WorkdirLock(tmp_path, owner="job-a").release()


def test_same_pid_does_not_reenter_or_release_foreign_lock(tmp_path: Path):
    from workflows.infrastructure.boundary.manifest import WorkdirLock

    first = WorkdirLock(tmp_path, owner_pid=555)
    first.acquire()
    first.drop_local()
    second = WorkdirLock(tmp_path, owner_pid=555)
    with pytest.raises(BoundaryError) as exc:
        second.acquire()
    assert exc.value.code == "BOUNDARY_WORKDIR_BUSY"
    second.release()
    assert (tmp_path / "boundary" / ".boundary.lock").is_file()
    WorkdirLock(tmp_path, owner=first.owner).release()
    assert not (tmp_path / "boundary" / ".boundary.lock").is_file()


def test_same_owner_token_can_reenter(tmp_path: Path):
    from workflows.infrastructure.boundary.manifest import WorkdirLock

    first = WorkdirLock(tmp_path, owner="job-token")
    first.acquire()
    first.drop_local()
    second = WorkdirLock(tmp_path, owner="job-token")
    second.acquire()
    second.release()
    assert not (tmp_path / "boundary" / ".boundary.lock").is_file()


def _hotstart_workdir(tmp_path: Path) -> Path:
    import yaml

    workdir = tmp_path / "case"
    workdir.mkdir()
    (workdir / "restart.ww3").write_bytes(b"original-restart")
    (workdir / "checkpoint.ww3").write_bytes(b"requested-checkpoint")
    (workdir / "ww3_shel.nml").write_text(
        "&DOMAIN_NML\n  DOMAIN%START  = '20000101 000000'\n/\n",
        encoding="utf-8",
    )
    raw = _minimal_raw()
    raw["workdir"] = {"path": str(workdir)}
    raw["ww3"]["restart"] = {
        "mode": "restart",
        "pick_latest_checkpoint": False,
        "restart_time": "20000101 060000",
        "restart_file": "checkpoint.ww3",
    }
    (workdir / "params.yml").write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    return workdir


def test_regular_workflow_does_not_prepare_hotstart_while_locked(tmp_path: Path):
    from workflows.infrastructure.boundary.manifest import WorkdirLock
    from workflows.infrastructure.local.run_service import LocalRunService

    workdir = _hotstart_workdir(tmp_path)
    holder = WorkdirLock(workdir, owner="job-holder")
    holder.acquire()
    try:
        rc = LocalRunService()._workflow_regular(workdir, "/nonexistent", lambda _m: None, 1)
        assert rc == 1
        assert (workdir / "restart.ww3").read_bytes() == b"original-restart"
        nml = (workdir / "ww3_shel.nml").read_text(encoding="utf-8")
        assert "20000101 000000" in nml
        assert "20000101 060000" not in nml
        assert (workdir / "boundary" / ".boundary.lock").is_file()
    finally:
        holder.release()


def test_runtime_lock_phase_busy_leaves_restart_untouched(tmp_path: Path):
    from workflows.infrastructure.boundary.manifest import WorkdirLock
    from workflows.infrastructure.boundary.runtime import main as boundary_main

    workdir = _hotstart_workdir(tmp_path)
    holder = WorkdirLock(workdir, owner="job-holder")
    holder.acquire()
    try:
        rc = boundary_main(["--workdir", str(workdir), "--phase", "lock", "--lock-owner", "job-b"])
        assert rc == 1
        assert (workdir / "restart.ww3").read_bytes() == b"original-restart"
    finally:
        holder.release()


def test_scripts_acquire_lock_before_hotstart():
    root = Path(__file__).resolve().parents[2]
    for rel in ("public/scripts/local.sh", "public/scripts/server.sh"):
        text = (root / rel).read_text(encoding="utf-8")
        marker = text.find('if [ "$GRID_TYPE" = "nested" ]; then')
        assert marker >= 0
        nested_part, regular_part = text[marker:].split("# Regular grid mode", 1)
        assert nested_part.find("run_boundary_runtime lock") < nested_part.find("prepare_nested_restart")
        assert nested_part.find("prepare_nested_restart") < nested_part.find("run_boundary_runtime pregrid")
        assert regular_part.find("run_boundary_runtime lock") < regular_part.find("prepare_regular_restart")
        assert regular_part.find("prepare_regular_restart") < regular_part.find("run_boundary_runtime pregrid")


def test_disable_prepare_requires_lock(tmp_path: Path):
    from workflows.application.boundary_preparation import prepare_boundary_inputs
    from workflows.infrastructure.boundary.manifest import (
        WorkdirLock,
        record_managed_file,
        save_manifest,
        sha256_file,
    )

    workdir = tmp_path / "case"
    workdir.mkdir()
    nest = workdir / "nest.ww3"
    nest.write_bytes(b"managed-nest")
    manifest = {"schema_version": 1, "files": []}
    record_managed_file(
        manifest,
        relpath="nest.ww3",
        kind="nest.ww3",
        sha256=sha256_file(nest),
        run_id="job-a",
    )
    save_manifest(workdir, manifest)
    (workdir / "boundary" / "mask_origin.json").write_text(
        '{"filename": "grid.mask_nobound", "idla": 1, "idfm": 1}\n',
        encoding="utf-8",
    )
    (workdir / "ww3_grid.nml").write_text(
        "&MASK_NML\n  MASK%FILENAME = 'boundary/grid.mask_boundary'\n  MASK%IDLA = 1\n/\n",
        encoding="utf-8",
    )
    (workdir / "boundary" / "grid.mask_boundary").write_text("1 2\n", encoding="utf-8")
    (workdir / "grid.mask_nobound").write_text("1 1\n", encoding="utf-8")
    raw = _minimal_raw()
    raw["workdir"] = {"path": str(workdir)}
    cfg = parse_pipeline_config(raw, base_dir=workdir, validation_stage="plot")
    assert cfg.boundary.enabled is False
    holder = WorkdirLock(workdir, owner="job-holder")
    holder.acquire()
    try:
        with pytest.raises(BoundaryError) as exc:
            prepare_boundary_inputs(cfg)
        assert exc.value.code == "BOUNDARY_WORKDIR_BUSY"
        assert nest.is_file()
        assert "grid.mask_boundary" in (workdir / "ww3_grid.nml").read_text(encoding="utf-8")
    finally:
        holder.release()
    result = prepare_boundary_inputs(cfg)
    assert result.state == "disabled"
    assert not nest.is_file()


def test_linear_mapping_accepts_swapped_equal_weights():
    from workflows.domain.boundary_models import BoundaryMapping
    from workflows.infrastructure.boundary.ww3_bounc_nml import NestFileInfo, compare_mapping_with_nest

    target = BoundaryTargetPoint(point_id="i0002j0005", i=2, j=5, lon=120.25, lat=11.0, sides=["west"])
    mapping = BoundaryMapping(
        target_id="i0002j0005",
        source_ids=["sta_a", "sta_b"],
        distances_km=[10.0, 10.0],
        weights=[0.5, 0.5],
        method="linear",
        covered=True,
    )
    info = NestFileInfo()
    info.nbi = 1
    info.xb = [120.25]
    info.yb = [11.0]
    info.mapping_indices = [[2, 1]]
    info.mapping_weights = [[0.5, 0.5]]
    compare_mapping_with_nest(
        [mapping],
        [target],
        info,
        method="linear",
        source_index={"sta_a": 1, "sta_b": 2},
    )


def test_linear_mapping_rejects_weight_mismatch_after_swap():
    from workflows.domain.boundary_models import BoundaryMapping
    from workflows.infrastructure.boundary.ww3_bounc_nml import NestFileInfo, compare_mapping_with_nest

    target = BoundaryTargetPoint(point_id="i0002j0005", i=2, j=5, lon=120.25, lat=11.0, sides=["west"])
    mapping = BoundaryMapping(
        target_id="i0002j0005",
        source_ids=["sta_a", "sta_b"],
        distances_km=[10.0, 20.0],
        weights=[0.7, 0.3],
        method="linear",
        covered=True,
    )
    info = NestFileInfo()
    info.nbi = 1
    info.xb = [120.25]
    info.yb = [11.0]
    info.mapping_indices = [[2, 1]]
    info.mapping_weights = [[0.7, 0.3]]
    with pytest.raises(BoundaryError) as exc:
        compare_mapping_with_nest(
            [mapping],
            [target],
            info,
            method="linear",
            source_index={"sta_a": 1, "sta_b": 2},
        )
    assert exc.value.code == "BOUNDARY_VERIFY_FAILED"


def test_sample_compare_requires_tpiinv_scale(tmp_path: Path):
    import math
    from datetime import timedelta

    from workflows.domain.boundary_models import BoundaryPlan
    from workflows.infrastructure.boundary.spectra_normalizer import write_station_file
    from workflows.infrastructure.boundary.ww3_bounc_nml import NestFileInfo, sample_compare_nest_spectra

    times = [datetime(2000, 1, 1, tzinfo=timezone.utc) + timedelta(hours=h) for h in range(2)]
    freqs = np.array([0.08, 0.088])
    dirs = np.array([0.0, 90.0, 180.0, 270.0])
    efth = np.ones((2, 2, 4)) * 2.0
    rel = "boundary/normalized/s1.nc"
    write_station_file(
        tmp_path / rel,
        name="s1",
        lon=120.0,
        lat=10.0,
        times=times,
        frequencies=freqs,
        directions=dirs,
        efth=efth,
    )
    plan = BoundaryPlan(normalized_relpaths=[rel])
    tpiinv = 1.0 / (2.0 * math.pi)
    ok = NestFileInfo()
    ok.spectra = [[efth[0] * tpiinv], [efth[1] * tpiinv]]
    sample_compare_nest_spectra(ok, tmp_path, plan)
    naked = NestFileInfo()
    naked.spectra = [[efth[0]], [efth[1]]]
    with pytest.raises(BoundaryError) as exc:
        sample_compare_nest_spectra(naked, tmp_path, plan)
    assert exc.value.code == "BOUNDARY_VERIFY_FAILED"


def test_same_process_worker_cannot_reenter_without_owner(tmp_path: Path):
    import threading

    from workflows.infrastructure.boundary.manifest import WorkdirLock

    outer = WorkdirLock(tmp_path)
    outer.acquire()
    out: list[str] = []

    def attempt() -> None:
        inner = WorkdirLock(tmp_path)
        try:
            inner.acquire()
            out.append("acquired")
            inner.release()
        except BoundaryError as exc:
            out.append(exc.code)

    thread = threading.Thread(target=attempt)
    thread.start()
    thread.join()
    outer.release()
    assert out == ["BOUNDARY_WORKDIR_BUSY"]


def test_nest_nan_spectrum_fails(tmp_path: Path):
    import struct

    from workflows.infrastructure.boundary.ww3_bounc_nml import read_nest_file

    ident = b"WAVEWATCH III BOUNDARY DATA FILE"
    ver = b"III  1.03 "
    payload = ident + ver + struct.pack(">ii", 10, 24) + struct.pack(">fff", 1.1, 0.08, 3.0) + struct.pack(">i", 7)
    rec1 = struct.pack(">i", len(payload)) + payload + struct.pack(">i", len(payload))
    interp = bytes(7 * 40)
    rec2 = struct.pack(">i", len(interp)) + interp + struct.pack(">i", len(interp))
    timep = struct.pack(">iii", 20000101, 0, 7)
    rec3 = struct.pack(">i", 12) + timep + struct.pack(">i", 12)
    spec = bytearray(960)
    spec[0:4] = struct.pack(">f", float("nan"))
    rec4 = struct.pack(">i", 960) + bytes(spec) + struct.pack(">i", 960)
    nest = tmp_path / "nest.ww3"
    nest.write_bytes(rec1 + rec2 + rec3 + rec4 * 7)
    with pytest.raises(BoundaryError) as exc:
        read_nest_file(nest)
    assert exc.value.code == "BOUNDARY_VERIFY_FAILED"
