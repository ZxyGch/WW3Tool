"""谱文件读取与规范化。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest

from workflows.infrastructure.boundary.spectra_normalizer import infer_direction_convention, write_station_file
from workflows.infrastructure.boundary.spectra_reader import inspect_spectra_file, read_station_efth


def test_write_and_inspect_one_station(tmp_path: Path):
    times = [datetime(2000, 1, 1, tzinfo=timezone.utc) + timedelta(hours=h) for h in range(3)]
    freqs = np.array([0.04, 0.044, 0.0484])
    dirs = np.array([0.0, 90.0, 180.0, 270.0])
    efth = np.zeros((3, 3, 4))
    efth[:, 1, 0] = 2.5
    path = tmp_path / "s1.nc"
    write_station_file(
        path,
        name="sta1",
        lon=122.0,
        lat=31.0,
        times=times,
        frequencies=freqs,
        directions=dirs,
        efth=efth,
    )
    meta = inspect_spectra_file(str(path))
    assert meta.n_stations == 1
    assert infer_direction_convention(meta) == "to_direction"
    assert "rad" in meta.efth_units
    _times, _f, _d, data = read_station_efth(str(path), 0)
    assert data.shape[0] == 3
    assert float(data[0, 1, 0]) == 2.5


def test_masked_fill_value_rejected(tmp_path: Path):
    from netCDF4 import Dataset

    from workflows.infrastructure.boundary.errors import BoundaryError
    from workflows.infrastructure.boundary.spectra_normalizer import sanitize_efth

    times = [datetime(2000, 1, 1, tzinfo=timezone.utc)]
    path = tmp_path / "missing.nc"
    write_station_file(
        path,
        name="source",
        lon=120.0,
        lat=10.0,
        times=times,
        frequencies=np.array([0.08, 0.088]),
        directions=np.array([0.0, 90.0, 180.0, 270.0]),
        efth=np.ones((1, 2, 4)),
    )
    with Dataset(path, "r+") as ds:
        ds.variables["efth"][0, 0, 0, 0] = np.ma.masked
    with pytest.raises(BoundaryError) as exc:
        _t, _f, _d, arr = read_station_efth(path, 0)
        sanitize_efth(arr)
    assert exc.value.code == "BOUNDARY_INVALID_SPECTRA"


def test_thoff_clamped_like_w3gridmd():
    """w3gridmd: RTH0 = MAX(-0.5, MIN(0.5, RTH0))。越界 THOFF 必须与夹取后同轴。"""
    from workflows.infrastructure.boundary.spectrum_coords import target_spectral_discrete

    ref = target_spectral_discrete(0.08, 1.1, 10, 24, 0.5)
    for over in (0.5001, 1.0, 2.0, 37.0):
        got = target_spectral_discrete(0.08, 1.1, 10, 24, over)
        assert got.directions_deg == ref.directions_deg, over
        assert got.thoff == 0.5
    ref_lo = target_spectral_discrete(0.08, 1.1, 10, 24, -0.5)
    for under in (-0.5001, -1.0, -3.0):
        got = target_spectral_discrete(0.08, 1.1, 10, 24, under)
        assert got.directions_deg == ref_lo.directions_deg, under
        assert got.thoff == -0.5


def test_thoff_in_range_unchanged():
    """[-0.5, 0.5] 内的 THOFF 不得被改动。"""
    from workflows.infrastructure.boundary.spectrum_coords import target_spectral_discrete

    assert target_spectral_discrete(0.08, 1.1, 10, 24, 0.0).directions_deg[:3] == [90.0, 75.0, 60.0]
    assert target_spectral_discrete(0.08, 1.1, 10, 24, 0.5).directions_deg[0] == 82.5
    assert target_spectral_discrete(0.08, 1.1, 10, 24, 0.25).thoff == 0.25


def test_xfr_and_freq1_clamped_like_w3gridmd():
    """w3gridmd: XFR = MAX(RXFR, 1.00001)、FR1 = MAX(RFR1, 1.E-6)。"""
    from workflows.infrastructure.boundary.spectrum_coords import target_spectral_discrete

    flat = target_spectral_discrete(0.08, 1.0, 4, 24, 0.0).frequencies_hz
    assert flat == target_spectral_discrete(0.08, 1.00001, 4, 24, 0.0).frequencies_hz
    assert flat[1] > flat[0]  # XFR=1 会造成全同频率，WW3 不允许
    tiny = target_spectral_discrete(0.0, 1.1, 4, 24, 0.0).frequencies_hz
    assert tiny[0] == 1.0e-6
