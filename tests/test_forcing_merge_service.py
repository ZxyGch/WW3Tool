from __future__ import annotations

import shutil
from pathlib import Path

import netCDF4 as nc
import numpy as np
import pytest

from workflows.infrastructure.forcing.merge_service import (
    analyze_merge_inputs,
    merge_forcing_netcdf,
)


def _write_forcing(
    path: Path,
    *,
    times: list[float],
    variables: tuple[str, ...] = ("u10", "v10"),
    units: str = "hours since 2025-01-01 00:00:00",
    lat: tuple[float, ...] = (10.0, 11.0),
    time_last: bool = False,
    value_offset: float = 0.0,
) -> None:
    with nc.Dataset(path, "w") as ds:
        ds.title = "merge test"
        ds.createDimension("time", None)
        ds.createDimension("latitude", len(lat))
        ds.createDimension("longitude", 2)
        time = ds.createVariable("time", "f8", ("time",))
        time.units = units
        time.calendar = "standard"
        time[:] = times
        latitude = ds.createVariable("latitude", "f4", ("latitude",))
        latitude[:] = lat
        longitude = ds.createVariable("longitude", "f4", ("longitude",))
        longitude[:] = [120.0, 121.0]
        static = ds.createVariable("land_mask", "i1", ("latitude", "longitude"))
        static[:] = [[0, 1], [1, 0]]
        dims = ("latitude", "longitude", "time") if time_last else ("time", "latitude", "longitude")
        for var_index, name in enumerate(variables):
            var = ds.createVariable(name, "f4", dims, fill_value=-32767.0, zlib=True)
            var.units = "m/s"
            shape = (2, 2, len(times)) if time_last else (len(times), 2, 2)
            data = np.arange(np.prod(shape), dtype="f4").reshape(shape)
            var[:] = data + value_offset + var_index * 100


def test_time_concat_sorts_converts_units_and_preserves_metadata(tmp_path: Path) -> None:
    later = tmp_path / "later.nc"
    earlier = tmp_path / "earlier.nc"
    output = tmp_path / "merged.nc"
    _write_forcing(
        later,
        times=[24, 25],
        units="hours since 2025-01-01 00:00:00",
        time_last=True,
        value_offset=20,
    )
    _write_forcing(
        earlier,
        times=[0, 3600],
        units="seconds since 2025-01-01 00:00:00",
        time_last=True,
        value_offset=0,
    )

    analysis = analyze_merge_inputs([str(later), str(earlier)])
    assert analysis.valid
    assert analysis.time_steps == 4
    merge_forcing_netcdf([str(later), str(earlier)], str(output))

    with nc.Dataset(output) as ds:
        assert ds.title == "merge test"
        assert ds.variables["u10"]._FillValue == -32767.0
        assert ds.variables["u10"].filters()["zlib"]
        assert ds.variables["u10"].dimensions == ("latitude", "longitude", "time")
        assert ds.variables["land_mask"][:].shape == (2, 2)
        assert ds.dimensions["time"].isunlimited()
        assert ds.variables["time"].units == "seconds since 1970-01-01 00:00:00"
        assert np.all(np.diff(ds.variables["time"][:]) > 0)


def test_duplicate_time_equal_is_deduplicated_and_conflict_is_rejected(tmp_path: Path) -> None:
    first = tmp_path / "first.nc"
    same = tmp_path / "same.nc"
    conflict = tmp_path / "conflict.nc"
    _write_forcing(first, times=[0, 1])
    _write_forcing(same, times=[0, 1])
    _write_forcing(conflict, times=[0, 1], value_offset=1)

    output = tmp_path / "deduplicated.nc"
    merge_forcing_netcdf([str(first), str(same)], str(output))
    with nc.Dataset(output) as ds:
        assert len(ds.dimensions["time"]) == 2

    analysis = analyze_merge_inputs([str(first), str(conflict)])
    assert not analysis.valid
    assert "conflict.nc" in analysis.errors[0]


def test_merges_compatible_different_fields_and_supports_time_last(tmp_path: Path) -> None:
    wind = tmp_path / "wind.nc"
    ice = tmp_path / "ice.nc"
    output = tmp_path / "combined.nc"
    _write_forcing(wind, times=[0, 1], time_last=True)
    _write_forcing(ice, times=[0, 1], variables=("siconc",), time_last=True)

    analysis = analyze_merge_inputs([str(wind), str(ice)])
    assert analysis.valid
    assert analysis.strategy
    merge_forcing_netcdf([str(wind), str(ice)], str(output))

    with nc.Dataset(output) as ds:
        assert ds.variables["u10"].dimensions == ("latitude", "longitude", "time")
        assert ds.variables["siconc"].dimensions == ("latitude", "longitude", "time")
        assert ds.variables["u10"].shape[-1] == 2


def test_rejects_incompatible_fields_and_does_not_leave_partial_output(tmp_path: Path) -> None:
    wind = tmp_path / "wind.nc"
    ice = tmp_path / "ice.nc"
    output = tmp_path / "combined.nc"
    _write_forcing(wind, times=[0, 1])
    _write_forcing(ice, times=[0, 2], variables=("siconc",), lat=(10.0, 12.0))
    output.write_text("existing")

    analysis = analyze_merge_inputs([str(wind), str(ice)])
    assert not analysis.valid
    with pytest.raises(ValueError):
        merge_forcing_netcdf([str(wind), str(ice)], str(output))
    assert output.read_text() == "existing"
    assert not list(tmp_path.glob(".combined.nc.*.tmp"))


def test_rejects_output_that_is_also_an_input(tmp_path: Path) -> None:
    first = tmp_path / "first.nc"
    second = tmp_path / "second.nc"
    _write_forcing(first, times=[0])
    _write_forcing(second, times=[1], value_offset=10)
    with pytest.raises(ValueError):
        merge_forcing_netcdf([str(first), str(second)], str(first))


def test_repository_era5_sample_no_longer_fails_on_fill_value(tmp_path: Path) -> None:
    sample = Path("public/forcing/era5_wind.nc")
    if not sample.exists():
        pytest.skip("repository forcing sample is unavailable")
    second = tmp_path / "era5_copy.nc"
    shutil.copyfile(sample, second)
    output = tmp_path / "era5.nc"
    merge_forcing_netcdf([str(sample), str(second)], str(output))
    with nc.Dataset(output) as ds:
        assert "_FillValue" in ds.variables["u10"].ncattrs()
