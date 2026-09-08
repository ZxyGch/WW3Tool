"""强迫场时间与经度覆盖的实际 NetCDF 回归样例。"""

import sys
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np
import pytest
from netCDF4 import Dataset

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from workflows.application.forcing_coverage_checker import (
    check_lonlat_coverage, check_time_range_coverage, validate_ww3_forcing_time,
)
from workflows.application.local_run import run_local
from workflows.domain.config_models import PipelineConfig, WorkdirConfig, ForcingVariableOverride
from workflows.domain.forcing_fields import Step2Files
from workflows.infrastructure.adapters.ww3_namelist_adapter import prepare_ww3_files
from workflows.support.logging import CoreLogger


def make_forcing(path, *, lons=None, times=(0, 24), time_name="time", coordinate_names=("longitude", "latitude")):
    """写入尺寸很小、具有真实时间和坐标元数据的风场。"""
    lons = list(range(100, 141)) if lons is None else lons
    lon_name, lat_name = coordinate_names
    with Dataset(path, "w") as ds:
        for name, size in ((lon_name, len(lons)), (lat_name, 3), (time_name, len(times))):
            ds.createDimension(name, size)
        ds.createVariable(lon_name, "f8", (lon_name,))[:] = lons
        ds.createVariable(lat_name, "f8", (lat_name,))[:] = [-20, 0, 20]
        t = ds.createVariable(time_name, "f8", (time_name,))
        t.units = "hours since 2020-01-01 00:00:00"
        t[:] = times
        for name in ("u10", "v10"):
            ds.createVariable(name, "f4", (time_name, lat_name, lon_name))[:] = 1
    return path


@pytest.mark.parametrize("lons,grid_lon,covered", [
    (range(100, 141), (170, 190), False),
    (range(100, 141), (170, -170), False),
    (range(160, 201), (170, -170), True),
    (range(160, 201), (-190, -170), True),
    ([170, 175, 180, -175, -170], (175, -175), True),
    ([-180, -175, -170, 170, 175], (175, -175), True),
    (range(160, 201), (-10, 10), False),
    (range(-170, 171), (175, -175), False),
    (range(-170, 171), (-150, 150), True),
    (range(190, 231), (-170, -130), True),
    (range(100, 141), (110, 130), True),
    (range(100, 141), (0, 360), False),
    (np.arange(0, 360, 0.25), (-180, 180), True),
    (range(-180, 180), (170, -170), True),
    (range(-180, 181), (0, 360), True),
    (range(359, -1, -1), (170, 190), True),
    (range(0, 351), (350, 359), False),
    (range(100, 141), (99.9998, 140.0002), True),
])
def test_longitude_coverage(tmp_path, lons, grid_lon, covered):
    path = make_forcing(tmp_path / "wind.nc", lons=lons)
    issues = check_lonlat_coverage(*grid_lon, -10, 10, {"wind": path}, {"wind": "风场"})
    assert (not issues) == covered
    assert not issues or issues[0].issue_type == "insufficient"


def test_global_longitude_does_not_bypass_latitude(tmp_path):
    path = make_forcing(tmp_path / "wind.nc", lons=range(360))
    assert check_lonlat_coverage(0, 360, -30, 30, {"wind": path}, {})


def test_custom_coordinates_and_invalid_coordinate(tmp_path):
    path = make_forcing(tmp_path / "wind.nc", coordinate_names=("XLONG", "XLAT"))
    mapping = {"wind": {"longitude": "XLONG", "latitude": "XLAT"}}
    assert not check_lonlat_coverage(110, 130, -10, 10, {"wind": path}, {}, variable_names=mapping)
    with Dataset(path, "a") as ds:
        ds.variables["XLONG"][0] = np.nan
    issues = check_lonlat_coverage(110, 130, -10, 10, {"wind": path}, {}, variable_names=mapping)
    assert issues[0].issue_type == "read_failed"


@pytest.mark.parametrize("times,start,end,issue", [
    ((0, 24), "20200101", "20200102", None),
    ((0, 24), "20200101", "20200110", "insufficient"),
    ((6, 24), "20200101", "20200102", "insufficient"),
    ((0, 18), "20200101", "20200101 230000", "insufficient"),
    ((24, 0), "20200101", "20200102", "read_failed"),
    ((0, 0, 24), "20200101", "20200102", "read_failed"),
    ((0, np.nan), "20200101", "20200102", "read_failed"),
])
def test_time_coverage(tmp_path, times, start, end, issue):
    path = make_forcing(tmp_path / "wind.nc", times=times)
    issues = check_time_range_coverage(start, end, {"wind": path}, {})
    assert (issues[0].issue_type if issues else None) == issue


def test_missing_or_unreadable_time_is_an_issue(tmp_path):
    path = tmp_path / "missing.nc"
    assert check_time_range_coverage("20200101", "20200102", {"wind": path}, {})[0].error
    make_forcing(path)
    with Dataset(path, "a") as ds:
        ds.variables["time"].delncattr("units")
    assert check_time_range_coverage("20200101", "20200102", {"wind": path}, {})[0].issue_type == "read_failed"


@pytest.fixture
def config(tmp_path):
    cfg = PipelineConfig(source_path=None, base_dir=tmp_path, workdir=WorkdirConfig(tmp_path))
    cfg.ww3.start_date, cfg.ww3.end_date, cfg.ww3.output_step = "20200101", "20200110", "3600"
    cfg.forcing.wind = make_forcing(tmp_path / "wind.nc")
    return cfg


def test_shared_namelist_entry_blocks_before_writing(config):
    with patch("workflows.infrastructure.adapters.ww3_namelist_adapter._WW3Adapter") as adapter:
        with pytest.raises(ValueError, match="20200110"):
            prepare_ww3_files(config, Step2Files(wind=str(config.forcing.wind)), CoreLogger())
        adapter.assert_not_called()


def test_cli_and_desktop_share_the_time_gate(config):
    from workflows.interfaces.command_line import _run_prepare_ww3
    from desktop.view_models.pipeline import PipelineViewModel

    with pytest.raises(ValueError, match="20200110"):
        _run_prepare_ww3(config)
    result = PipelineViewModel().apply_ww3_params(config)
    assert result.error and "20200110" in result.error
    assert not (config.workdir.path / "ww3_shel.nml").exists()


def test_local_run_does_not_start_with_insufficient_forcing(config):
    service = Mock()
    result = run_local(config, service)
    assert not result.success
    service.run_workflow.assert_not_called()


def test_pipeline_checks_prepared_file_after_cropping(config):
    from workflows.application.preprocessing_workflow import run_pipeline

    prepared_file = config.forcing.wind
    config.forcing.wind = make_forcing(config.workdir.path / "source.nc", times=(0, 240))
    with patch("workflows.application.preprocessing_workflow.prepare_forcing",
               return_value=Step2Files(wind=str(prepared_file))):
        with pytest.raises(ValueError, match="20200110"):
            run_pipeline(config, skip_grid=True)


def test_custom_source_time_and_valid_run(config):
    config.ww3.end_date = "20200102"
    config.forcing.wind = make_forcing(config.workdir.path / "custom.nc", time_name="forecast_clock")
    config.forcing.custom["wind"] = ForcingVariableOverride(time="forecast_clock")
    validate_ww3_forcing_time(config, Step2Files(wind=str(config.forcing.wind)), CoreLogger())


def test_server_visible_file_uses_configured_source_time(config):
    config.ww3.end_date = "20200102"
    path = make_forcing(config.workdir.path / "server.nc", time_name="forecast_clock")
    config.forcing.remote_paths["wind"] = str(path)
    config.forcing.custom["wind"] = ForcingVariableOverride(time="forecast_clock")
    # 服务器路径文件使用源时间名；清单中的输出时间名只描述标准化产物。
    (config.workdir.path / "forcing_manifest.json").write_text('{"wind":{"file":"server.nc","time":"time"}}')
    validate_ww3_forcing_time(config, Step2Files(wind=str(path)), CoreLogger())


def test_valid_local_forcing_allows_model_to_start(config):
    config.ww3.end_date = "20200102"
    service = Mock()
    service.run_workflow.return_value = 0
    assert run_local(config, service).success
    service.run_workflow.assert_called_once()


def test_remote_unavailable_is_explicit_and_local_run_rejects_it(config):
    config.forcing.wind = None
    remote = "/synthetic-server-only/wind.nc"
    config.forcing.remote_paths["wind"] = remote
    logger = CoreLogger()
    validate_ww3_forcing_time(config, Step2Files(wind=remote), logger)
    assert any(remote in message for message in logger.messages)
    with pytest.raises(ValueError):
        validate_ww3_forcing_time(config, Step2Files(wind=remote), CoreLogger(), allow_remote=False)
