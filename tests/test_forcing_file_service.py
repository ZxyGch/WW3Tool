from pathlib import Path

import netCDF4 as nc
import numpy as np

from workflows.infrastructure.forcing.file_service import FileService
from workflows.support.logging import CoreLogger


def _write_forcing(
    path: Path,
    *,
    latitude: tuple[float, ...] | None = (10.0, 11.0),
    longitude: tuple[float, ...] = (122.0, 121.0, 120.0),
) -> np.ndarray:
    with nc.Dataset(path, "w") as ds:
        ds.title = "coordinate flip test"
        ds.createDimension("time", None)
        if latitude is not None:
            ds.createDimension("y", len(latitude))
        ds.createDimension("x", len(longitude))

        time = ds.createVariable("time", "f8", ("time",))
        time.units = "hours since 2025-01-01"
        time.calendar = "standard"
        time[:] = [0.0, 1.0]

        if latitude is not None:
            lat = ds.createVariable("latitude", "f4", ("y",))
            lat[:] = latitude
        lon = ds.createVariable("longitude", "f4", ("x",))
        lon[:] = longitude

        dimensions = ("time", "y", "x") if latitude is not None else ("time", "x")
        shape = (2, len(latitude), len(longitude)) if latitude is not None else (2, len(longitude))
        values = np.arange(np.prod(shape), dtype=np.float32).reshape(shape)
        field = ds.createVariable(
            "field",
            "f4",
            dimensions,
            fill_value=-32767.0,
            zlib=True,
            complevel=2,
        )
        field.units = "m/s"
        field[:] = values

        static_dimensions = ("y", "x") if latitude is not None else ("x",)
        static = ds.createVariable("static", "i2", static_dimensions)
        static[...] = values[0]
    return values


def test_flips_longitude_dimension_when_coordinate_variable_uses_x(tmp_path: Path) -> None:
    source = tmp_path / "source.nc"
    target = tmp_path / "target.nc"
    values = _write_forcing(source)
    logger = CoreLogger()

    result = FileService(logger).copy_and_fix_forcing_file(str(source), str(target))

    assert result == str(target)
    with nc.Dataset(target) as ds:
        np.testing.assert_array_equal(ds.variables["longitude"][:], [120.0, 121.0, 122.0])
        np.testing.assert_array_equal(ds.variables["latitude"][:], [10.0, 11.0])
        np.testing.assert_array_equal(ds.variables["field"][:], values[..., ::-1])
        np.testing.assert_array_equal(ds.variables["static"][:], values[0, ..., ::-1])
        assert ds.variables["field"]._FillValue == -32767.0
        assert ds.variables["field"].filters()["zlib"]
        assert ds.variables["field"].filters()["complevel"] == 2
        assert ds.dimensions["time"].isunlimited()
        assert ds.title == "coordinate flip test"
    assert any("经度" in message for message in logger.messages)
    assert not (tmp_path / "target.nc.flip_tmp").exists()


def test_flips_both_coordinates_and_all_matching_data_axes(tmp_path: Path) -> None:
    source = tmp_path / "source.nc"
    target = tmp_path / "target.nc"
    values = _write_forcing(source, latitude=(12.0, 11.0, 10.0))

    result = FileService().copy_and_fix_forcing_file(str(source), str(target))

    assert result == str(target)
    with nc.Dataset(target) as ds:
        np.testing.assert_array_equal(ds.variables["latitude"][:], [10.0, 11.0, 12.0])
        np.testing.assert_array_equal(ds.variables["longitude"][:], [120.0, 121.0, 122.0])
        np.testing.assert_array_equal(ds.variables["field"][:], values[:, ::-1, ::-1])
        np.testing.assert_array_equal(ds.variables["static"][:], values[0, ::-1, ::-1])


def test_flips_longitude_when_latitude_coordinate_is_absent(tmp_path: Path) -> None:
    source = tmp_path / "source.nc"
    target = tmp_path / "target.nc"
    values = _write_forcing(source, latitude=None)

    result = FileService().copy_and_fix_forcing_file(str(source), str(target))

    assert result == str(target)
    with nc.Dataset(target) as ds:
        np.testing.assert_array_equal(ds.variables["longitude"][:], [120.0, 121.0, 122.0])
        np.testing.assert_array_equal(ds.variables["field"][:], values[:, ::-1])


def test_rejects_non_monotonic_longitude(tmp_path: Path) -> None:
    source = tmp_path / "source.nc"
    target = tmp_path / "target.nc"
    _write_forcing(source, longitude=(120.0, 122.0, 121.0))
    logger = CoreLogger()

    result = FileService(logger).copy_and_fix_forcing_file(str(source), str(target))

    assert result is None
    assert any("经度" in message and "严格单调" in message for message in logger.messages)
    assert not (tmp_path / "target.nc.flip_tmp").exists()
