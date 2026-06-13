# -*- coding: utf-8 -*-
"""从 WW3 网格描述文件解析 RECT/CURV 几何信息。

支持三种常见来源：

- 扁平 ``grid.meta``（``RECT%NX`` 等键值行）；
- Fortran namelist（``&RECT_NML`` / ``&CURV_NML``）；
-  legacy 五行 ASCII 描述块。

解析结果用于可视化 worker 构建经纬度网格，以及 Step 4 将部分参数同步到 ``ww3_grid.nml``。

[EN] Parse RECT/CURV geometry information from WW3 grid description files.

Supports three common sources:

- Flat ``grid.meta`` (``RECT%NX``-style key-value lines);
- Fortran namelist (``&RECT_NML`` / ``&CURV_NML``);
- Legacy five-line ASCII description block.

The parsed results are used by the visualization worker to build lon/lat grids,
and by Step 4 to synchronize certain parameters into ``ww3_grid.nml``.
"""
from __future__ import annotations


def parse_rect_flat_meta(lines: list[str]) -> dict | None:
    """解析扁平 ``grid.meta``（无 ``&`` namelist 块的 ``RECT%`` 键值行）。

    [EN] Parse a flat ``grid.meta`` (``RECT%`` key-value lines without ``&`` namelist blocks).
    """
    vals: dict[str, float | int] = {}
    for raw in lines:
        line = raw.split("!")[0].strip()
        if not line or line.startswith("$"):
            continue
        if "=" not in line:
            continue
        key, _, rhs = line.partition("=")
        key_u = key.strip().upper()
        rhs = rhs.strip()
        if not rhs:
            continue
        tok = rhs.replace("'", "").replace('"', "").split()[0]
        if key_u == "RECT%NX":
            vals["nx"] = int(float(tok))
        elif key_u == "RECT%NY":
            vals["ny"] = int(float(tok))
        elif key_u == "RECT%SX":
            vals["sx"] = float(tok)
        elif key_u == "RECT%SY":
            vals["sy"] = float(tok)
        elif key_u == "RECT%X0":
            vals["x0"] = float(tok)
        elif key_u == "RECT%Y0":
            vals["y0"] = float(tok)
    needed = ("nx", "ny", "sx", "sy", "x0", "y0")
    if all(k in vals for k in needed):
        return {
            "grid_type": "RECT",
            "nx": int(vals["nx"]),
            "ny": int(vals["ny"]),
            "sx": float(vals["sx"]),
            "sy": float(vals["sy"]),
            "x0": float(vals["x0"]),
            "y0": float(vals["y0"]),
            "sf": 1.0,
            "sf0": 1.0,
        }
    return None


def _strip_assign_rhs(line: str) -> str:
    """从 namelist 赋值行提取右侧第一个 token（去掉注释与引号）。

    [EN] Extract the first right-hand token from a namelist assignment line (stripping comments and quotes).
    """
    if "=" not in line:
        return ""
    rhs = line.split("=", 1)[1].strip()
    if "!" in rhs:
        rhs = rhs.split("!", 1)[0].strip()
    return rhs.split()[0].strip("'\"") if rhs else ""


def parse_rect_from_namelist(lines: list[str]) -> dict | None:
    """解析 ``&RECT_NML ... /`` 块，返回 nx/ny/sx/sy/x0/y0（度）。

    [EN] Parse an ``&RECT_NML ... /`` block, returning nx/ny/sx/sy/x0/y0 (in degrees).
    """
    in_rect = False
    vals: dict[str, float | int] = {}
    for raw in lines:
        line = raw.split("!")[0].rstrip()
        s = line.strip()
        if not s:
            continue
        u = s.upper()
        if u.startswith("&RECT_NML"):
            in_rect = True
            vals = {}
            continue
        if in_rect:
            if s.startswith("/"):
                break
            if "RECT%NX" in u and "=" in s:
                vals["nx"] = int(float(_strip_assign_rhs(s)))
            elif "RECT%NY" in u and "=" in s:
                vals["ny"] = int(float(_strip_assign_rhs(s)))
            elif "RECT%SX" in u and "=" in s and "XCOORD" not in u:
                vals["sx"] = float(_strip_assign_rhs(s))
            elif "RECT%SY" in u and "=" in s and "YCOORD" not in u:
                vals["sy"] = float(_strip_assign_rhs(s))
            elif "RECT%X0" in u and "=" in s:
                vals["x0"] = float(_strip_assign_rhs(s))
            elif "RECT%Y0" in u and "=" in s:
                vals["y0"] = float(_strip_assign_rhs(s))
    needed = ("nx", "ny", "sx", "sy", "x0", "y0")
    if all(k in vals for k in needed):
        return {
            "grid_type": "RECT",
            "nx": int(vals["nx"]),
            "ny": int(vals["ny"]),
            "sx": float(vals["sx"]),
            "sy": float(vals["sy"]),
            "x0": float(vals["x0"]),
            "y0": float(vals["y0"]),
            "sf": 1.0,
            "sf0": 1.0,
        }
    return None


def parse_rect_legacy_ascii(lines: list[str]) -> dict | None:
    """解析 legacy 五行 ASCII（首行 ``RECT`` / ``CURV`` 标识的块）。

    [EN] Parse a legacy five-line ASCII block (identified by ``RECT`` / ``CURV`` on the first line).
    """
    grid_line_idx = None
    gtype = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("$"):
            continue
        tokens = stripped.replace("'", "").replace('"', "").split()
        if not tokens:
            continue
        if tokens[0].upper() in ("RECT", "CURV"):
            gtype = tokens[0].upper()
            grid_line_idx = i
            break
    if grid_line_idx is None or gtype != "RECT":
        return None
    if grid_line_idx + 3 >= len(lines):
        return None
    L1 = lines[grid_line_idx + 1].split()
    L2 = lines[grid_line_idx + 2].split()
    L3 = lines[grid_line_idx + 3].split()
    if len(L1) < 2 or len(L2) < 3 or len(L3) < 3:
        return None
    nx, ny = int(float(L1[0])), int(float(L1[1]))
    sf = float(L2[2])
    sf0 = float(L3[2])
    sx_deg = float(L2[0]) / sf
    sy_deg = float(L2[1]) / sf
    x0 = float(L3[0]) / sf0
    y0 = float(L3[1]) / sf0
    return {
        "grid_type": "RECT",
        "nx": nx,
        "ny": ny,
        "sx": sx_deg,
        "sy": sy_deg,
        "x0": x0,
        "y0": y0,
        "sf": sf,
        "sf0": sf0,
    }


def parse_curv_flat_meta(lines: list[str]) -> dict | None:
    """解析扁平 ``grid.meta`` 中的 CURV 曲线网格元数据。

    [EN] Parse CURV curvilinear grid metadata from a flat ``grid.meta``.
    """
    vals: dict[str, float | int | str] = {}
    for raw in lines:
        line = raw.split("!")[0].strip()
        if not line or line.startswith("$") or "=" not in line:
            continue
        key, _, rhs = line.partition("=")
        key_u = key.strip().upper()
        tok = rhs.strip().strip("'\"")
        if not tok:
            continue
        tok = tok.split()[0].strip("'\"")
        if key_u == "CURV%NX":
            vals["nx"] = int(float(tok))
        elif key_u == "CURV%NY":
            vals["ny"] = int(float(tok))
        elif key_u == "CURV%XCOORD%SF":
            vals["xcoord_sf"] = float(tok)
        elif key_u == "CURV%XCOORD%FILENAME":
            vals["xcoord_filename"] = str(tok)
        elif key_u == "CURV%YCOORD%SF":
            vals["ycoord_sf"] = float(tok)
        elif key_u == "CURV%YCOORD%FILENAME":
            vals["ycoord_filename"] = str(tok)
    needed = ("nx", "ny", "xcoord_sf", "xcoord_filename", "ycoord_sf", "ycoord_filename")
    if all(k in vals for k in needed):
        return {
            "grid_type": "CURV",
            "nx": int(vals["nx"]),
            "ny": int(vals["ny"]),
            "xcoord_sf": float(vals["xcoord_sf"]),
            "xcoord_filename": str(vals["xcoord_filename"]),
            "ycoord_sf": float(vals["ycoord_sf"]),
            "ycoord_filename": str(vals["ycoord_filename"]),
        }
    return None


def parse_curv_from_namelist(lines: list[str]) -> dict | None:
    """解析 ``&CURV_NML ... /`` 块，含曲线坐标文件名与缩放因子。

    [EN] Parse a ``&CURV_NML ... /`` block, containing curvilinear coordinate file names and scale factors.
    """
    in_curv = False
    vals: dict[str, float | int | str] = {}
    for raw in lines:
        line = raw.split("!")[0].rstrip()
        s = line.strip()
        if not s:
            continue
        u = s.upper()
        if u.startswith("&CURV_NML"):
            in_curv = True
            vals = {}
            continue
        if in_curv:
            if s.startswith("/"):
                break
            if "CURV%NX" in u and "=" in s:
                vals["nx"] = int(float(_strip_assign_rhs(s)))
            elif "CURV%NY" in u and "=" in s:
                vals["ny"] = int(float(_strip_assign_rhs(s)))
            elif "CURV%XCOORD%SF" in u and "=" in s:
                vals["xcoord_sf"] = float(_strip_assign_rhs(s))
            elif "CURV%XCOORD%FILENAME" in u and "=" in s:
                vals["xcoord_filename"] = _strip_assign_rhs(s)
            elif "CURV%YCOORD%SF" in u and "=" in s:
                vals["ycoord_sf"] = float(_strip_assign_rhs(s))
            elif "CURV%YCOORD%FILENAME" in u and "=" in s:
                vals["ycoord_filename"] = _strip_assign_rhs(s)
    needed = ("nx", "ny", "xcoord_sf", "xcoord_filename", "ycoord_sf", "ycoord_filename")
    if all(k in vals for k in needed):
        return {
            "grid_type": "CURV",
            "nx": int(vals["nx"]),
            "ny": int(vals["ny"]),
            "xcoord_sf": float(vals["xcoord_sf"]),
            "xcoord_filename": str(vals["xcoord_filename"]),
            "ycoord_sf": float(vals["ycoord_sf"]),
            "ycoord_filename": str(vals["ycoord_filename"]),
        }
    return None


# Step 4 写入 ww3_grid.nml 时从 grid.meta 同步的键；其余键忽略。
# [EN] Keys synchronized from grid.meta when Step 4 writes ww3_grid.nml; other keys are ignored.
WW3_GRID_META_SYNC_KEY_MAP = {
    "GRID%TYPE": ("grid_type", str),
    "GRID%COORD": ("grid_coord", str),
    "GRID%CLOS": ("grid_clos", str),
    "RECT%NX": ("nx", int),
    "RECT%NY": ("ny", int),
    "RECT%SX": ("sx", float),
    "RECT%SY": ("sy", float),
    "RECT%X0": ("x0", float),
    "RECT%Y0": ("y0", float),
    "DEPTH%SF": ("depth_sf", float),
    "OBST%SF": ("obst_sf", float),
}


def parse_ww3_grid_meta_for_sync(path: str) -> dict | None:
    """读取 grid.meta，提取 Step 4 需同步到 ``ww3_grid.nml`` 的参数子集。

    支持扁平 ``KEY = value`` 行及 Fortran namelist 内相同键名。

    [EN] Read grid.meta and extract the subset of parameters that Step 4 needs to synchronize into ``ww3_grid.nml``.

    Supports both flat ``KEY = value`` lines and the same key names within Fortran namelists.
    """
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
    except OSError:
        return None
    out: dict = {}
    for raw in lines:
        line = raw.split("!")[0].strip()
        if not line or line.startswith("$"):
            continue
        if "=" not in line:
            continue
        key, _, rhs = line.partition("=")
        key_u = key.strip().upper()
        if key_u not in WW3_GRID_META_SYNC_KEY_MAP:
            continue
        name, typ = WW3_GRID_META_SYNC_KEY_MAP[key_u]
        rhs = rhs.strip()
        if not rhs:
            continue
        tok = rhs.split()[0].strip("'\"")
        try:
            if typ is int:
                out[name] = int(float(tok))
            elif typ is float:
                out[name] = float(tok)
            else:
                out[name] = str(tok)
        except (TypeError, ValueError):
            continue
    needed_rect = ("nx", "ny", "sx", "sy", "x0", "y0")
    if not all(k in out for k in needed_rect):
        return None
    return out


def parse_rect_grid_description(path: str) -> dict | None:
    """依次尝试 flat meta、namelist、legacy ASCII，解析 RECT 网格描述。

    [EN] Try flat meta, namelist, and legacy ASCII in order to parse a RECT grid description.
    """
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
    except OSError:
        return None
    r = parse_rect_flat_meta(lines)
    if r:
        return r
    r = parse_rect_from_namelist(lines)
    if r:
        return r
    return parse_rect_legacy_ascii(lines)


def parse_structured_grid_description(path: str) -> dict | None:
    """解析结构化网格描述，RECT 优先，失败则尝试 CURV。

    [EN] Parse a structured grid description, trying RECT first and falling back to CURV on failure.
    """
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
    except OSError:
        return None
    rect = parse_rect_flat_meta(lines)
    if rect:
        return rect
    rect = parse_rect_from_namelist(lines)
    if rect:
        return rect
    rect = parse_rect_legacy_ascii(lines)
    if rect:
        return rect
    curv = parse_curv_flat_meta(lines)
    if curv:
        return curv
    return parse_curv_from_namelist(lines)


def rect_lon_lat_mesh(path: str):
    """由 RECT 描述构建二维经纬度网格 ``(lon, lat)``；失败返回 ``(None, None)``。

    [EN] Build a 2D lon/lat mesh ``(lon, lat)`` from a RECT description; returns ``(None, None)`` on failure.
    """
    import numpy as np

    d = parse_rect_grid_description(path)
    if not d:
        return None, None
    nx, ny = d["nx"], d["ny"]
    lon1d = d["x0"] + np.arange(nx, dtype=float) * d["sx"]
    lat1d = d["y0"] + np.arange(ny, dtype=float) * d["sy"]
    lon, lat = np.meshgrid(lon1d, lat1d)
    return lon, lat


def structured_lon_lat_mesh(path: str):
    """由结构化网格描述（RECT 或 CURV）构建二维经纬度网格。

    [EN] Build a 2D lon/lat mesh from a structured grid description (RECT or CURV).
    """
    import os
    import numpy as np

    d = parse_structured_grid_description(path)
    if not d:
        return None, None
    if d.get("grid_type") == "RECT":
        return rect_lon_lat_mesh(path)

    base_dir = os.path.dirname(path)
    lon_path = os.path.join(base_dir, str(d["xcoord_filename"]))
    lat_path = os.path.join(base_dir, str(d["ycoord_filename"]))
    if not os.path.isfile(lon_path) or not os.path.isfile(lat_path):
        return None, None
    try:
        lon = np.loadtxt(lon_path, dtype=float)
        lat = np.loadtxt(lat_path, dtype=float)
    except Exception:
        return None, None
    lon = np.atleast_2d(lon) / float(d.get("xcoord_sf", 1.0) or 1.0)
    lat = np.atleast_2d(lat) / float(d.get("ycoord_sf", 1.0) or 1.0)
    if lon.shape != lat.shape:
        return None, None
    if lon.shape != (int(d["ny"]), int(d["nx"])):
        return None, None
    return lon, lat
