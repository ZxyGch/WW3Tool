"""球面距离、经度标准化与循环角距离。

经度标准化必须保留空间位置，禁止把日界线两侧相邻点判为相距一周。
"""

from __future__ import annotations

import math

EARTH_RADIUS_KM = 6371.0


def wrap_lon_delta_deg(delta: float) -> float:
    """把经差折到 (-180, 180]。"""
    return (float(delta) + 180.0) % 360.0 - 180.0


def wrap_lon_deg(lon: float) -> float:
    """折到 (-180, 180]，仅用于显示；距离计算使用 wrap_lon_delta_deg。"""
    return (float(lon) + 180.0) % 360.0 - 180.0


def haversine_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """两点球面距离（千米）。经差按最短弧，可跨日界线。"""
    phi1 = math.radians(float(lat1))
    phi2 = math.radians(float(lat2))
    dphi = phi2 - phi1
    dlam = math.radians(wrap_lon_delta_deg(float(lon2) - float(lon1)))
    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2.0) ** 2
    a = min(1.0, max(0.0, a))
    return 2.0 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def circular_abs_deg(a: float, b: float) -> float:
    """两个角度（度）的最小循环差的绝对值。"""
    return abs(wrap_lon_delta_deg(float(a) - float(b)))


def unit_vector(lon: float, lat: float) -> tuple[float, float, float]:
    lam = math.radians(float(lon))
    phi = math.radians(float(lat))
    c = math.cos(phi)
    return (c * math.cos(lam), c * math.sin(lam), math.sin(phi))


def ww3_bounc_linear_parameter(
    lon_a: float,
    lat_a: float,
    lon_b: float,
    lat_b: float,
    lon_p: float,
    lat_p: float,
) -> tuple[float, bool]:
    """``ww3_bounc`` INTERP=2 的经纬度平面投影参数 t。

    与 6.07/7.14 源码一致：经差折到 (−180, 180]，
    ``t = (Δλ_P·Δλ_AB + Δφ_P·Δφ_AB) / (Δλ_AB² + Δφ_AB²)``。
    WW3 随后把 t 夹到 [0,1]；首版在开区间 (0,1) 外视为覆盖失败。
    """
    dlon = wrap_lon_delta_deg(float(lon_b) - float(lon_a))
    dlat = float(lat_b) - float(lat_a)
    dlo = wrap_lon_delta_deg(float(lon_p) - float(lon_a))
    dlat_p = float(lat_p) - float(lat_a)
    dist2 = dlon * dlon + dlat * dlat
    if dist2 < 1e-24:
        return 0.0, False
    t = (dlo * dlon + dlat_p * dlat) / dist2
    interior = 0.0 < t < 1.0 and t == t and abs(t) != float("inf")
    return float(t), interior


def geodesic_segment_parameter(
    lon_a: float,
    lat_a: float,
    lon_b: float,
    lat_b: float,
    lon_p: float,
    lat_p: float,
) -> tuple[float, bool]:
    """把点 P 投影到 A–B 大圆弧上，返回参数 t 与是否落在开线段 (0,1) 内。

    t<0 或 t>1 表示投影在线段外（linear 首版视为覆盖失败）。
    A 与 B 重合时返回 (0.0, False)。
    """
    ax, ay, az = unit_vector(lon_a, lat_a)
    bx, by, bz = unit_vector(lon_b, lat_b)
    px, py, pz = unit_vector(lon_p, lat_p)
    cx = ay * bz - az * by
    cy = az * bx - ax * bz
    cz = ax * by - ay * bx
    n = math.sqrt(cx * cx + cy * cy + cz * cz)
    if n < 1e-12:
        return 0.0, False
    cx, cy, cz = cx / n, cy / n, cz / n
    # 投影到 A-B 所在大圆：P' = normalize(N × (P × N)) wait: P onto plane of A,B
    # plane normal is A×B = C. P_proj = normalize(P - (P·C)C) then angle from A.
    dot_pc = px * cx + py * cy + pz * cz
    qx, qy, qz = px - dot_pc * cx, py - dot_pc * cy, pz - dot_pc * cz
    qn = math.sqrt(qx * qx + qy * qy + qz * qz)
    if qn < 1e-12:
        return 0.0, False
    qx, qy, qz = qx / qn, qy / qn, qz / qn
    # signed angles from A to Q and A to B around C
    def ang(ux, uy, uz, vx, vy, vz) -> float:
        crx = uy * vz - uz * vy
        cry = uz * vx - ux * vz
        crz = ux * vy - uy * vx
        sin_a = crx * cx + cry * cy + crz * cz
        cos_a = ux * vx + uy * vy + uz * vz
        return math.atan2(sin_a, cos_a)

    ab = ang(ax, ay, az, bx, by, bz)
    aq = ang(ax, ay, az, qx, qy, qz)
    if abs(ab) < 1e-12:
        return 0.0, False
    t = aq / ab
    interior = 0.0 < t < 1.0
    return float(t), interior
