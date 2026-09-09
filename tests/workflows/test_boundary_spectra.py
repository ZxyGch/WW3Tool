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


def test_decode_station_name_char_array():
    """WW3 原生 station_name 是 (station, string16) 的 S1 字符数组。

    dtype.kind 也是 "S"，若先按一维字符串分支处理，会得到 "[b'w' b'0' ...]"。
    """
    import numpy as np

    from workflows.infrastructure.boundary.spectra_reader import _decode_names

    class _Var:
        def __init__(self, arr):
            self._arr = arr

        def __getitem__(self, item):
            return self._arr[item]

    def chars(text: str, width: int = 16):
        return np.frombuffer(text.ljust(width).encode("ascii"), dtype="S1")

    raw = np.stack([chars("w02"), chars("north_pt")])
    assert raw.dtype.kind == "S" and raw.ndim == 2  # 与 WW3 原生文件同形
    assert _decode_names(_Var(raw), 2) == ["w02", "north_pt"]
    # NUL 填充的站名同样要清干净
    nul = np.stack([np.frombuffer(b"w02" + b"\x00" * 13, dtype="S1")])
    assert _decode_names(_Var(nul), 1) == ["w02"]


def test_decode_station_name_string_array():
    """一维字符串/字节数组仍按原路径解码，并去掉 NUL 填充。"""
    import numpy as np

    from workflows.infrastructure.boundary.spectra_reader import _decode_names

    class _Var:
        def __init__(self, arr):
            self._arr = arr

        def __getitem__(self, item):
            return self._arr[item]

    assert _decode_names(_Var(np.array([b"aaa\x00", b"bbb "], dtype="S4")), 2) == ["aaa", "bbb"]
    assert _decode_names(_Var(np.array(["s1", "s2"], dtype="U2")), 2) == ["s1", "s2"]
    # 站数多于名字时补占位，不得越界
    assert _decode_names(_Var(np.array([b"only"], dtype="S4")), 3)[1:] == ["station_2", "station_3"]


def test_log_packed_ounp_units_rejected_with_actionable_hint():
    """ww3_ounp NCVARTYPE<=3 写 log10 打包谱，units 含 "rad" 但不是线性谱。

    必须在单位这一层拦下并指明改用 NCVARTYPE=4，不能落到下游"谱值为负"的误导报错。
    """
    import pytest

    from workflows.infrastructure.boundary.errors import BoundaryError
    from workflows.infrastructure.boundary.spectra_normalizer import efth_unit_scale

    with pytest.raises(BoundaryError) as exc:
        efth_unit_scale("log10(m2 s rad-1 +1E-12)")
    assert exc.value.code == "BOUNDARY_CONVENTION_UNKNOWN"
    assert any("NCVARTYPE=4" in h for h in exc.value.hints)


def test_linear_efth_units_still_accepted():
    """NCVARTYPE=4 的线性谱与每度谱不受影响。"""
    import math

    from workflows.infrastructure.boundary.spectra_normalizer import efth_unit_scale

    assert efth_unit_scale("m2 s rad-1") == (1.0, "m2 s rad-1")
    scale, unit = efth_unit_scale("m2 s degree-1")
    assert unit == "m2 s rad-1" and abs(scale - 180.0 / math.pi) < 1e-9
