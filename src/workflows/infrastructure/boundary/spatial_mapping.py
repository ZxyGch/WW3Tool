"""球面最近邻与两点线性映射预览。"""

from __future__ import annotations

from ...domain.boundary_models import (
    MAPPING_ALGO_VERSION,
    BoundaryMapping,
    BoundaryStation,
    BoundaryTargetPoint,
)
from .errors import BoundaryError
from .geo import haversine_km, ww3_bounc_linear_parameter
from ...support.translations import tr


def _stable_nearest(
    target: BoundaryTargetPoint,
    stations: list[BoundaryStation],
) -> tuple[BoundaryStation, float]:
    best: BoundaryStation | None = None
    best_d = float("inf")
    for station in stations:
        dist = haversine_km(target.lon, target.lat, station.lon, station.lat)
        if dist < best_d - 1e-12:
            best = station
            best_d = dist
        elif abs(dist - best_d) <= 1e-12 and best is not None:
            if station.source_id < best.source_id:
                best = station
                best_d = dist
    if best is None:
        raise BoundaryError("BOUNDARY_SPATIAL_COVERAGE", tr("boundary_no_source_station", "没有可用源站点"))
    return best, best_d


def _two_nearest(
    target: BoundaryTargetPoint,
    stations: list[BoundaryStation],
) -> tuple[BoundaryStation, float, BoundaryStation, float]:
    ranked: list[tuple[float, str, BoundaryStation]] = []
    for station in stations:
        dist = haversine_km(target.lon, target.lat, station.lon, station.lat)
        ranked.append((dist, station.source_id, station))
    ranked.sort(key=lambda item: (item[0], item[1]))
    if len(ranked) < 2:
        raise BoundaryError(
            "BOUNDARY_SPATIAL_COVERAGE",
            tr("boundary_linear_needs_two", "两点线性至少需要两个不同源站点"),
        )
    a = ranked[0]
    b = None
    for item in ranked[1:]:
        if haversine_km(a[2].lon, a[2].lat, item[2].lon, item[2].lat) > 1e-6:
            b = item
            break
    if b is None:
        raise BoundaryError(
            "BOUNDARY_SPATIAL_COVERAGE",
            tr("boundary_linear_same_location", "两点线性的两个源点位置不能相同"),
            context={"target_id": target.point_id},
        )
    return a[2], a[0], b[2], b[0]


def map_targets(
    targets: list[BoundaryTargetPoint],
    stations: list[BoundaryStation],
    *,
    method: str,
    max_distance_km: float,
) -> list[BoundaryMapping]:
    if max_distance_km is None or float(max_distance_km) <= 0:
        raise BoundaryError(
            "BOUNDARY_SPATIAL_COVERAGE",
            tr("boundary_max_distance_required", "启用外部谱后必须填写正的 max_distance_km"),
        )
    method = str(method or "nearest").lower()
    if method not in {"nearest", "linear"}:
        raise BoundaryError("BOUNDARY_SPATIAL_COVERAGE", tr("boundary_unknown_method", "未知插值方法 {method}").format(method=method))
    if not stations:
        raise BoundaryError("BOUNDARY_SPATIAL_COVERAGE", tr("boundary_no_stations_to_map", "没有源站点可映射"))
    mappings: list[BoundaryMapping] = []
    failed: list[str] = []
    for target in targets:
        if method == "nearest":
            station, dist = _stable_nearest(target, stations)
            covered = dist <= float(max_distance_km) + 1e-12
            mappings.append(
                BoundaryMapping(
                    target_id=target.point_id,
                    source_ids=[station.source_id],
                    distances_km=[float(dist)],
                    weights=[1.0],
                    method="nearest",
                    covered=covered,
                )
            )
            if not covered:
                failed.append(target.point_id)
            continue
        s1, d1, s2, d2 = _two_nearest(target, stations)
        if d1 > float(max_distance_km) or d2 > float(max_distance_km):
            mappings.append(
                BoundaryMapping(
                    target_id=target.point_id,
                    source_ids=[s1.source_id, s2.source_id],
                    distances_km=[float(d1), float(d2)],
                    weights=[0.0, 0.0],
                    method="linear",
                    covered=False,
                    notes=["source_beyond_max_distance"],
                )
            )
            failed.append(target.point_id)
            continue
        t, interior = ww3_bounc_linear_parameter(s1.lon, s1.lat, s2.lon, s2.lat, target.lon, target.lat)
        if not interior or not np_finite(t):
            mappings.append(
                BoundaryMapping(
                    target_id=target.point_id,
                    source_ids=[s1.source_id, s2.source_id],
                    distances_km=[float(d1), float(d2)],
                    weights=[float(1.0 - min(max(t, 0.0), 1.0)), float(min(max(t, 0.0), 1.0))],
                    method="linear",
                    covered=False,
                    degenerate=True,
                    notes=["linear_extrapolation_clamped"],
                )
            )
            failed.append(target.point_id)
            continue
        w2 = float(t)
        w1 = float(1.0 - t)
        mappings.append(
            BoundaryMapping(
                target_id=target.point_id,
                source_ids=[s1.source_id, s2.source_id],
                distances_km=[float(d1), float(d2)],
                weights=[w1, w2],
                method="linear",
                covered=True,
            )
        )
    if failed:
        raise BoundaryError(
            "BOUNDARY_SPATIAL_COVERAGE",
            tr("boundary_targets_uncovered", "{n_failed} 个目标点超出距离上限或线性退化").format(n_failed=len(failed)),
            context={"failed_ids": failed[:30], "n_failed": len(failed), "method": method},
            hints=[tr("boundary_hint_check_map", "查看地图并调整源点、范围或改为 nearest")],
        )
    return mappings


def np_finite(value: float) -> bool:
    return value == value and abs(value) != float("inf")


def involved_source_ids(mappings: list[BoundaryMapping]) -> list[str]:
    seen: list[str] = []
    for item in mappings:
        for source_id in item.source_ids:
            if source_id not in seen:
                seen.append(source_id)
    return seen


def write_mapping_csv(path, mappings: list[BoundaryMapping]) -> None:
    from pathlib import Path

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("target_id,method,covered,degenerate,source_ids,distances_km,weights,notes,algo\n")
        for item in mappings:
            handle.write(
                f"{item.target_id},{item.method},{int(item.covered)},{int(item.degenerate)},"
                f"{'|'.join(item.source_ids)},"
                f"{'|'.join(f'{d:.6f}' for d in item.distances_km)},"
                f"{'|'.join(f'{w:.8f}' for w in item.weights)},"
                f"{'|'.join(item.notes)},{MAPPING_ALGO_VERSION}\n"
            )


def read_mapping_csv(path) -> list[BoundaryMapping]:
    from pathlib import Path

    path = Path(path)
    mappings: list[BoundaryMapping] = []
    if not path.is_file():
        return mappings
    with path.open("r", encoding="utf-8") as handle:
        header = handle.readline()
        if not header:
            return mappings
        for line in handle:
            parts = line.rstrip("\n").split(",")
            if len(parts) < 7:
                continue
            mappings.append(
                BoundaryMapping(
                    target_id=parts[0],
                    method=parts[1],
                    covered=parts[2] in {"1", "True", "true"},
                    degenerate=parts[3] in {"1", "True", "true"},
                    source_ids=[p for p in parts[4].split("|") if p],
                    distances_km=[float(p) for p in parts[5].split("|") if p],
                    weights=[float(p) for p in parts[6].split("|") if p],
                    notes=[p for p in (parts[7] if len(parts) > 7 else "").split("|") if p],
                )
            )
    return mappings
