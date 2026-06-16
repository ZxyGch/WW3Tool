from datetime import datetime

import numpy as np

from workflows.infrastructure.plot.spectrum_worker import (
    _decode_time_values,
    _direction_label_position,
    _find_spectrum_files,
    _ww3_direction_to_radians,
)
from workflows.infrastructure.plot.workers_utils import _collect_station_lon_lat


class _TimeVar:
    units = "hours since 2020-01-02 03:00:00"
    calendar = "standard"


def test_decode_time_values_uses_netcdf_units() -> None:
    decoded = _decode_time_values(np.array([0.0, 6.0, 24.0]), _TimeVar())

    assert decoded == [
        datetime(2020, 1, 2, 3),
        datetime(2020, 1, 2, 9),
        datetime(2020, 1, 3, 3),
    ]


def test_ww3_direction_mapping_uses_east_origin_counterclockwise() -> None:
    assert np.isclose(_ww3_direction_to_radians(0.0), 0.0)
    assert np.isclose(_ww3_direction_to_radians(90.0), np.pi / 2)

    east = _direction_label_position(0.0, 2.0)
    north = _direction_label_position(90.0, 2.0)

    assert np.allclose(east, (2.0, 0.0), atol=1e-12)
    assert np.allclose(north, (0.0, 2.0), atol=1e-12)


def test_find_spectrum_files_are_sorted(tmp_path) -> None:
    second = tmp_path / "ww3.2015_spec.nc"
    first = tmp_path / "ww3.2014_spec.nc"
    second.touch()
    first.touch()

    assert _find_spectrum_files(str(tmp_path)) == [str(first), str(second)]
    assert _find_spectrum_files(str(tmp_path), str(second)) == [str(second)]


def test_collect_station_lon_lat_uses_station_axis_not_flattened_time_axis() -> None:
    lon = np.array(
        [
            [123.0, 123.234, 123.481, 123.742],
            [123.0, 123.234, 123.481, 123.742],
        ]
    )
    lat = np.array(
        [
            [31.0, 33.2395, 35.4786, 37.7172],
            [31.0, 33.2395, 35.4786, 37.7172],
        ]
    )

    assert _collect_station_lon_lat(lon, lat, 4) == [
        (123.0, 31.0),
        (123.234, 33.2395),
        (123.481, 35.4786),
        (123.742, 37.7172),
    ]
