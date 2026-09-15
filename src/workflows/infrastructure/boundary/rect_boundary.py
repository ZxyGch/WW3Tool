"""从实际网格产物生成向内一格活动边界点与派生掩码。"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterable

import numpy as np

from ...domain.boundary_models import (
    SELECTION_ALGO_VERSION,
    BoundaryTargetPoint,
    point_id,
)
from ..grid_visualization.rect_grid_desc_parse import parse_structured_grid_description
from ..grid_visualization.structured_grid_paths import structured_grid_desc_path
from .errors import BoundaryError
from .nml_text import effective_nml_assignments, is_nml_comment, strip_nml_comment


SEA_MASK_VALUES = {1, 2}
LAND_MASK_VALUES = {0, 3, -1, -2, 7}


def _parse_nml_assignments(nml_path: Path) -> dict[str, str]:
    if not nml_path.is_file():
        return {}
    return effective_nml_assignments(nml_path.read_text(encoding="utf-8", errors="replace"))
    pattern = re.compile(r"^[ \t]*!?[ \t]*([A-Za-z0-9%]+)\s*=\s*(.+)$")
    for raw in nml_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.split("!")[0].strip()
        match = pattern.match(raw if "=" in raw else "")
        if not match:
            match = pattern.match(line)
        if not match:
            continue
        key = match.group(1).strip().upper()
        rhs = match.group(2).strip().rstrip("/").strip()
        if rhs.startswith("'") or rhs.startswith('"'):
            rhs = rhs.strip("'\"").strip()
        else:
            rhs = rhs.split()[0] if rhs else ""
        values[key] = rhs
    return values


def load_rect_geometry(workdir: Path) -> dict:
    """读取实际网格产物与最终 ww3_grid.nml，禁止只用 GUI 范围估算索引。"""
    nml_path = workdir / "ww3_grid.nml"
    nml = _parse_nml_assignments(nml_path)
    desc = None
    desc_path = structured_grid_desc_path(str(workdir))
    if desc_path:
        try:
            desc = parse_structured_grid_description(desc_path)
        except (TypeError, ValueError, IndexError):
            desc = None
    geo: dict = {}
    if desc:
        geo.update(desc)
    for key, nml_key in (
        ("nx", "RECT%NX"),
        ("ny", "RECT%NY"),
        ("sx", "RECT%SX"),
        ("sy", "RECT%SY"),
        ("x0", "RECT%X0"),
        ("y0", "RECT%Y0"),
        ("depth_sf", "DEPTH%SF"),
        ("depth_idla", "DEPTH%IDLA"),
        ("mask_idla", "MASK%IDLA"),
        ("mask_idfm", "MASK%IDFM"),
        ("mask_filename", "MASK%FILENAME"),
        ("depth_filename", "DEPTH%FILENAME"),
        ("grid_clos", "GRID%CLOS"),
        ("grid_type", "GRID%TYPE"),
    ):
        if nml.get(nml_key):
            raw = nml[nml_key]
            if key in {"nx", "ny", "mask_idla", "mask_idfm", "depth_idla"}:
                try:
                    geo[key] = int(float(raw))
                except ValueError:
                    pass
            elif key in {"sx", "sy", "x0", "y0", "depth_sf"}:
                try:
                    geo[key] = float(raw)
                except ValueError:
                    pass
            else:
                geo[key] = raw
    needed = ("nx", "ny", "sx", "sy", "x0", "y0")
    missing = [k for k in needed if k not in geo]
    if missing:
        raise BoundaryError(
            "BOUNDARY_GRID_UNSUPPORTED",
            "无法从网格产物读取 RECT 几何",
            context={"missing": missing, "workdir": str(workdir)},
        )
    geo["depth_sf"] = float(geo.get("depth_sf") or nml.get("DEPTH%SF") or 1.0)
    geo["mask_idla"] = int(geo.get("mask_idla") or 1)
    geo["mask_idfm"] = int(geo.get("mask_idfm") or 1)
    geo["depth_idla"] = int(geo.get("depth_idla") or geo["mask_idla"])
    geo["nml_path"] = str(nml_path)
    geo["clos"] = str(geo.get("grid_clos") or nml.get("GRID%CLOS") or "").upper().strip("'\"")
    geo["grid_type"] = str(geo.get("grid_type") or nml.get("GRID%TYPE") or "RECT").upper().strip("'\"")
    return geo


def _reshape_field(values: np.ndarray, nx: int, ny: int, idla: int) -> np.ndarray:
    arr = np.asarray(values).reshape(-1)
    if arr.size != nx * ny:
        raise BoundaryError(
            "BOUNDARY_GRID_UNSUPPORTED",
            f"掩码/水深元素数 {arr.size} 与 NX*NY={nx*ny} 不一致",
            context={"size": int(arr.size), "nx": nx, "ny": ny},
        )
    if idla in {1, 2}:
        # 自南向北逐行，每行自西向东
        return arr.reshape((ny, nx))
    if idla in {3, 4}:
        return arr.reshape((ny, nx))[::-1]
    raise BoundaryError(
        "BOUNDARY_GRID_UNSUPPORTED",
        f"首版不支持 MASK%IDLA={idla}",
        context={"idla": idla},
    )


def read_ww3_field(path: Path, nx: int, ny: int, idla: int) -> np.ndarray:
    if not path.is_file():
        raise BoundaryError(
            "BOUNDARY_SOURCE_MISSING",
            f"网格文件不存在：{path}",
            context={"path": str(path)},
        )
    values = np.loadtxt(path)
    return _reshape_field(values, nx, ny, idla)


def write_mask_idla1(path: Path, mask: np.ndarray) -> None:
    """自由格式、南到北逐行，IDLA=1、IDFM=1。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    ny, nx = mask.shape
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for j in range(ny):
            row = " ".join(str(int(v)) for v in mask[j, :])
            handle.write(row + "\n")


def base_mask_path(workdir: Path, geo: dict) -> Path:
    named = geo.get("mask_filename")
    if named:
        candidate = workdir / str(named)
        if candidate.is_file() and candidate.name != "grid.mask_boundary":
            return candidate
    nobound = workdir / "grid.mask_nobound"
    if nobound.is_file():
        return nobound
    fallback = workdir / "grid.mask"
    if fallback.is_file():
        return fallback
    raise BoundaryError(
        "BOUNDARY_SOURCE_MISSING",
        "找不到基础掩码 grid.mask_nobound",
        context={"workdir": str(workdir)},
    )


def depth_path(workdir: Path, geo: dict) -> Path | None:
    named = geo.get("depth_filename")
    if named:
        candidate = workdir / str(named)
        if candidate.is_file():
            return candidate
    bot = workdir / "grid.bot"
    return bot if bot.is_file() else None


def lonlat_of(geo: dict, i: int, j: int) -> tuple[float, float]:
    """一基索引 (i,j) 的经纬度。"""
    lon = float(geo["x0"]) + (int(i) - 1) * float(geo["sx"])
    lat = float(geo["y0"]) + (int(j) - 1) * float(geo["sy"])
    return lon, lat


def ring_indices(nx: int, ny: int, sides: Iterable[str]) -> dict[tuple[int, int], set[str]]:
    """向内一格边界环，角点按 (i,j) 去重并保留所属边集合。"""
    chosen = {str(s).lower() for s in sides}
    cells: dict[tuple[int, int], set[str]] = {}

    def add(i: int, j: int, side: str) -> None:
        cells.setdefault((i, j), set()).add(side)

    if "west" in chosen:
        for j in range(2, ny):
            add(2, j, "west")
    if "east" in chosen:
        for j in range(2, ny):
            add(nx - 1, j, "east")
    if "south" in chosen:
        for i in range(2, nx):
            add(i, 2, "south")
    if "north" in chosen:
        for i in range(2, nx):
            add(i, ny - 1, "north")
    return cells


def is_wet(mask_val: int, depth_m: float | None) -> bool:
    if int(mask_val) not in SEA_MASK_VALUES:
        return False
    if depth_m is None:
        return True
    if not np.isfinite(depth_m):
        return False
    # grid.bot 为正水深且 DEPTH%SF=-1 时，缩放后为负高程；0 为干出。
    return abs(float(depth_m)) > 0.0


def build_target_points(
    workdir: Path,
    sides: Iterable[str],
    *,
    inset_cells: int = 1,
) -> tuple[list[BoundaryTargetPoint], np.ndarray, dict]:
    if int(inset_cells) != 1:
        raise BoundaryError(
            "BOUNDARY_GRID_UNSUPPORTED",
            "首版 inset_cells 固定为 1",
            context={"inset_cells": inset_cells},
        )
    geo = load_rect_geometry(workdir)
    if str(geo.get("grid_type") or "RECT").upper() not in {"RECT", "RECTILINEAR"}:
        raise BoundaryError(
            "BOUNDARY_GRID_UNSUPPORTED",
            f"首版仅支持结构化经纬度矩形网格，当前 GRID%TYPE={geo.get('grid_type')}",
            context={"grid_type": geo.get("grid_type")},
        )
    clos = str(geo.get("clos") or "")
    if clos in {"SMPL", "SMAP", "GLOBAL"} or "PERIOD" in clos:
        raise BoundaryError(
            "BOUNDARY_GRID_UNSUPPORTED",
            "首版不支持周期/全球闭合网格",
            context={"GRID%CLOS": clos},
        )
    nx, ny = int(geo["nx"]), int(geo["ny"])
    if nx < 4 or ny < 4:
        raise BoundaryError(
            "BOUNDARY_GRID_UNSUPPORTED",
            "网格尺寸不足以形成边界环和内部海点",
            context={"nx": nx, "ny": ny},
        )
    mask_file = base_mask_path(workdir, geo)
    origin = load_or_capture_mask_origin(workdir, geo)
    origin_file = workdir / str(origin["filename"])
    if origin_file.is_file():
        mask_file = origin_file
    mask = read_ww3_field(mask_file, nx, ny, int(origin["idla"]))
    depth = None
    dpath = depth_path(workdir, geo)
    if dpath is not None:
        raw = read_ww3_field(dpath, nx, ny, int(geo.get("depth_idla") or origin["idla"]))
        depth = raw.astype(np.float64) * float(geo["depth_sf"])
    existing_boundary: list[tuple[int, int]] = []
    selected = ring_indices(nx, ny, sides)
    selected_set = set(selected)
    for j in range(ny):
        for i in range(nx):
            if int(mask[j, i]) == 2:
                ij = (i + 1, j + 1)
                if ij not in selected_set:
                    existing_boundary.append(ij)
    if existing_boundary:
        raise BoundaryError(
            "BOUNDARY_MASK_CONFLICT",
            "基础掩码已有未纳入本次选择的活动边界点",
            context={"conflict_ij": existing_boundary[:20], "n": len(existing_boundary)},
        )
    points: list[BoundaryTargetPoint] = []
    empty_sides: list[str] = []
    side_hits = {s: 0 for s in {x.lower() for x in sides}}
    for (i, j), edge_set in selected.items():
        mask_val = int(mask[j - 1, i - 1])
        depth_m = None if depth is None else float(depth[j - 1, i - 1])
        if not is_wet(mask_val, depth_m):
            continue
        lon, lat = lonlat_of(geo, i, j)
        ordered_sides = [s for s in ("west", "east", "south", "north") if s in edge_set]
        points.append(
            BoundaryTargetPoint(
                point_id=point_id(i, j),
                i=i,
                j=j,
                lon=lon,
                lat=lat,
                sides=ordered_sides,
            )
        )
        for s in ordered_sides:
            side_hits[s] = side_hits.get(s, 0) + 1
    for side, n in side_hits.items():
        if n == 0:
            empty_sides.append(side)
    points.sort(key=lambda p: (p.j, p.i))
    if not points:
        raise BoundaryError(
            "BOUNDARY_NO_WET_POINTS",
            "全部所选边均无有效海点",
            context={"sides": list(sides), "empty_sides": empty_sides},
        )
    # 内部海点
    interior = 0
    for j in range(2, ny - 1):
        for i in range(2, nx - 1):
            if (i + 1, j + 1) in selected_set:
                continue
            mask_val = int(mask[j, i])
            depth_m = None if depth is None else float(depth[j, i])
            if is_wet(mask_val, depth_m) and mask_val == 1:
                interior += 1
    if interior < 1:
        raise BoundaryError(
            "BOUNDARY_GRID_UNSUPPORTED",
            "边界环没有内部计算海点",
            context={"nx": nx, "ny": ny},
        )
    derived = mask.copy()
    for pt in points:
        derived[pt.j - 1, pt.i - 1] = 2
    geo["empty_sides"] = empty_sides
    geo["base_mask_path"] = str(mask_file)
    geo["selection_algo_version"] = SELECTION_ALGO_VERSION
    geo["interior_sea_points"] = interior
    return points, derived, geo


def write_target_points_csv(path: Path, points: list[BoundaryTargetPoint]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("point_id,i,j,lon,lat,sides\n")
        for pt in points:
            handle.write(
                f"{pt.point_id},{pt.i},{pt.j},{pt.lon:.8f},{pt.lat:.8f},"
                f"{'|'.join(pt.sides)}\n"
            )


def read_target_points_csv(path: Path) -> list[BoundaryTargetPoint]:
    points: list[BoundaryTargetPoint] = []
    if not path.is_file():
        return points
    with path.open("r", encoding="utf-8") as handle:
        header = handle.readline()
        if not header:
            return points
        for line in handle:
            parts = line.rstrip("\n").split(",")
            if len(parts) < 5:
                continue
            points.append(
                BoundaryTargetPoint(
                    point_id=parts[0],
                    i=int(parts[1]),
                    j=int(parts[2]),
                    lon=float(parts[3]),
                    lat=float(parts[4]),
                    sides=[s for s in (parts[5].split("|") if len(parts) > 5 else []) if s],
                )
            )
    return points


def set_mask_nml(nml_path: Path, filename: str, *, idla: int = 1, idfm: int = 1) -> None:
    """把 MASK%FILENAME/IDLA/IDFM 写到 ww3_grid.nml 的 &MASK_NML 段。"""
    if not nml_path.is_file():
        raise BoundaryError("BOUNDARY_SOURCE_MISSING", f"找不到 {nml_path}")
    lines = nml_path.read_text(encoding="utf-8").splitlines(keepends=True)
    wanted = {
        "MASK%FILENAME": f"'{filename}'",
        "MASK%IDLA": str(int(idla)),
        "MASK%IDFM": str(int(idfm)),
    }
    found = {key: False for key in wanted}
    out: list[str] = []
    in_mask = False
    for line in lines:
        stripped = line.lstrip()
        commented = is_nml_comment(line)
        body = stripped[1:].lstrip() if commented else stripped
        # 组的起止只认未注释行：模板里注释掉的 "!&MASK_NML … !/" 说明块不得被写入有效赋值。
        # 真实组内注释掉的 MASK%FILENAME 等行仍按原设计替换为有效赋值。
        if not commented and re.match(r"^&MASK_NML\b", body, re.IGNORECASE):
            in_mask = True
            out.append(line)
            continue
        if in_mask and not commented and strip_nml_comment(body).strip() == "/":
            for key, value in wanted.items():
                if not found[key]:
                    out.append(f"  {key:14s} =  {value}\n")
                    found[key] = True
            in_mask = False
            out.append(line)
            continue
        if in_mask:
            assignment = strip_nml_comment(body)
            replaced = False
            for key, value in wanted.items():
                if re.search(rf"{re.escape(key)}\s*=", assignment, re.IGNORECASE):
                    newline = "\r\n" if line.endswith("\r\n") else "\n"
                    out.append(f"  {key:14s} =  {value}{newline}")
                    found[key] = True
                    replaced = True
                    break
            if replaced:
                continue
        out.append(line)
    nml_path.write_text("".join(out), encoding="utf-8")


MASK_ORIGIN_REL = "boundary/mask_origin.json"


def mask_origin_path(workdir: Path) -> Path:
    return Path(workdir) / MASK_ORIGIN_REL


def read_mask_origin(workdir: Path) -> dict | None:
    """只读取已记录的原始掩码参数，禁止在指纹核对时改写。"""
    path = mask_origin_path(workdir)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    filename = str(payload.get("filename") or "").strip()
    if not filename or payload.get("idla") in {None, ""}:
        return None
    return {
        "filename": filename,
        "idla": int(payload["idla"]),
        "idfm": int(payload.get("idfm") or 1),
    }


def load_or_capture_mask_origin(workdir: Path, geo: dict) -> dict:
    """首次准备时记下原始 MASK%FILENAME/IDLA/IDFM，禁止再次准备时按派生 IDLA=1 读基础掩码。"""
    existing = read_mask_origin(workdir)
    if existing is not None:
        return existing
    named = str((geo or {}).get("mask_filename") or "")
    if Path(named).name == "grid.mask_boundary":
        raise BoundaryError(
            "BOUNDARY_STALE",
            "缺少 boundary/mask_origin.json，禁止按派生 IDLA=1 掩码再次准备",
            hints=["把 ww3_grid.nml 的 MASK%FILENAME/IDLA 恢复为首次准备前的值后再准备"],
        )
    if not named and not (geo or {}).get("mask_idla"):
        return {"filename": "grid.mask_nobound", "idla": 1, "idfm": 1}
    named = named or "grid.mask"
    origin = {
        "filename": named,
        "idla": int((geo or {}).get("mask_idla") or 1),
        "idfm": int((geo or {}).get("mask_idfm") or 1),
    }
    path = mask_origin_path(workdir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(origin, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return origin


def restore_base_mask_nml(workdir: Path) -> None:
    """关闭边界时恢复原始掩码文件名和 IDLA/IDFM。"""
    nml = Path(workdir) / "ww3_grid.nml"
    if not nml.is_file():
        return
    origin_file = mask_origin_path(workdir)
    origin = read_mask_origin(workdir) if origin_file.is_file() else None
    if origin is not None:
        filename = str(origin["filename"])
        if not (Path(workdir) / filename).is_file():
            filename = "grid.mask_nobound" if (Path(workdir) / "grid.mask_nobound").is_file() else "grid.mask"
        set_mask_nml(nml, filename, idla=int(origin["idla"]), idfm=int(origin["idfm"]))
        return
    restore = "grid.mask_nobound" if (Path(workdir) / "grid.mask_nobound").is_file() else "grid.mask"
    if (Path(workdir) / restore).is_file():
        geo = load_rect_geometry(workdir)
        set_mask_nml(nml, restore, idla=int(geo.get("mask_idla") or 1), idfm=int(geo.get("mask_idfm") or 1))
