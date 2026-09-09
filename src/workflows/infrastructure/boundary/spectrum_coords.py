"""目标谱离散：由 SPECTRUM%FREQ1/XFR/NK/NTH/THOFF 解析。"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np

from ...domain.boundary_models import ANGLE_TOL_DEG, FREQ_ATOL_HZ, FREQ_RTOL, SpectralDiscrete
from .errors import BoundaryError


def geometric_frequencies(freq1: float, xfr: float, nk: int) -> np.ndarray:
    k = np.arange(int(nk), dtype=np.float64)
    return np.asarray(freq1, dtype=np.float64) * np.power(np.asarray(xfr, dtype=np.float64), k)


def clamp_thoff(thoff: float) -> float:
    """复刻 ``w3gridmd`` 的 ``RTH0 = MAX(-0.5, MIN(0.5, RTH0))``。

    WW3 读入 THOFF 后先夹到 [-0.5, 0.5] 再建方向轴；不夹就会按用户写的越界值
    算出与 WW3 实际相差整数个方向箱的轴，且没有任何下游检查能发现。
    """
    return max(-0.5, min(0.5, float(thoff)))


def clamp_xfr(xfr: float) -> float:
    """复刻 ``w3gridmd`` 的 ``XFR = MAX(RXFR, 1.00001)``。"""
    return max(float(xfr), 1.00001)


def clamp_freq1(freq1: float) -> float:
    """复刻 ``w3gridmd`` 的 ``FR1 = MAX(RFR1, 1.E-6)``。"""
    return max(float(freq1), 1.0e-6)


def ww3_internal_theta_rad(nth: int, thoff: float) -> np.ndarray:
    """WW3 内部方向：从正东起逆时针、传播去向，弧度。

    ``ww3_grid``：``TH(ITH) = DTH * (THOFF + ITH - 1)``，ITH=1..NTH，DTH=2π/NTH。
    THOFF=0 时 TH(1)=0（正东）。禁止写成 ITH-1.5。
    THOFF 先按 WW3 夹到 [-0.5, 0.5]。
    """
    nth = int(nth)
    dth = 2.0 * math.pi / float(nth)
    ith = np.arange(1, nth + 1, dtype=np.float64)
    return dth * (clamp_thoff(thoff) + ith - 1.0)


def nautical_to_direction_deg(theta_rad: np.ndarray) -> np.ndarray:
    """内部笛卡尔方向 → 从真北顺时针的传播去向（度，[0,360)）。

    与 ``ww3_ounp`` 一致：``DIR = MOD(450 - THD, 360)``，THD 为内部方向的度数。
    THOFF=0、NTH=24 时为 90°、75°、60°。禁止用 270−θ（那是来向）。
    """
    thd = np.degrees(np.asarray(theta_rad, dtype=np.float64))
    return np.mod(450.0 - thd, 360.0)


def target_spectral_discrete(freq1: float, xfr: float, nk: int, nth: int, thoff: float) -> SpectralDiscrete:
    """目标谱离散。FREQ1/XFR/THOFF 先按 ``w3gridmd`` 的夹取规则处理再建轴。"""
    freqs = geometric_frequencies(clamp_freq1(freq1), clamp_xfr(xfr), nk)
    dirs = nautical_to_direction_deg(ww3_internal_theta_rad(nth, thoff))
    return SpectralDiscrete(
        frequencies_hz=[float(v) for v in freqs],
        directions_deg=[float(v) for v in dirs],
        thoff=clamp_thoff(thoff),
        units="m2 s rad-1",
        direction_convention="to_direction",
    )


def frequencies_match(source: np.ndarray, target: np.ndarray) -> bool:
    src = np.asarray(source, dtype=np.float64).reshape(-1)
    tgt = np.asarray(target, dtype=np.float64).reshape(-1)
    if src.size != tgt.size:
        return False
    return bool(np.allclose(src, tgt, rtol=FREQ_RTOL, atol=FREQ_ATOL_HZ))


def directions_match(source: np.ndarray, target: np.ndarray) -> bool:
    src = np.asarray(source, dtype=np.float64).reshape(-1)
    tgt = np.asarray(target, dtype=np.float64).reshape(-1)
    if src.size != tgt.size:
        return False
    d = np.abs(((src - tgt + 180.0) % 360.0) - 180.0)
    return bool(np.all(d <= ANGLE_TOL_DEG))


def cyclic_permutation_offset(source: np.ndarray, target: np.ndarray) -> int | None:
    """若 source 经循环移位后与 target 匹配，返回移位 k（source 向左移 k）。"""
    src = np.asarray(source, dtype=np.float64).reshape(-1)
    tgt = np.asarray(target, dtype=np.float64).reshape(-1)
    n = src.size
    if n != tgt.size or n == 0:
        return None
    for k in range(n):
        rolled = np.roll(src, -k)
        d = np.abs(((rolled - tgt + 180.0) % 360.0) - 180.0)
        if np.all(d <= ANGLE_TOL_DEG):
            return k
    return None


def parse_spectrum_from_nml(nml_path: Path, parameters: dict[str, str] | None = None) -> SpectralDiscrete:
    """从最终 ww3_grid.nml 与可选配置参数解析谱离散。THOFF 缺省为 0。"""
    values: dict[str, float] = {
        "SPECTRUM%FREQ1": 0.0,
        "SPECTRUM%XFR": 1.0,
        "SPECTRUM%NK": 0.0,
        "SPECTRUM%NTH": 0.0,
        "SPECTRUM%THOFF": 0.0,
    }
    if parameters:
        for key, raw in parameters.items():
            ukey = str(key).strip().upper()
            if ukey in values and raw is not None and str(raw).strip():
                values[ukey] = float(raw)
    if nml_path.is_file():
        text = nml_path.read_text(encoding="utf-8", errors="replace")
        import re

        for key in list(values):
            pattern = re.compile(
                rf"^[ \t]*!?[ \t]*{re.escape(key)}\s*=\s*([^\s!/]+)",
                re.IGNORECASE | re.MULTILINE,
            )
            match = pattern.search(text)
            if match:
                try:
                    values[key] = float(match.group(1).strip().strip("'\""))
                except ValueError:
                    pass
    nk = int(values["SPECTRUM%NK"])
    nth = int(values["SPECTRUM%NTH"])
    if nk < 1 or nth < 1:
        raise BoundaryError(
            "BOUNDARY_SPECTRAL_MISMATCH",
            "无法从 ww3_grid.nml 解析有效的 NK/NTH",
            context={"path": str(nml_path), "nk": nk, "nth": nth},
        )
    return target_spectral_discrete(
        values["SPECTRUM%FREQ1"],
        values["SPECTRUM%XFR"],
        nk,
        nth,
        values["SPECTRUM%THOFF"],
    )


def spectral_fingerprint(spec: SpectralDiscrete) -> str:
    freqs = ",".join(f"{v:.12g}" for v in spec.frequencies_hz)
    dirs = ",".join(f"{v:.12g}" for v in spec.directions_deg)
    return f"thoff={spec.thoff:.12g}|f={freqs}|d={dirs}"
