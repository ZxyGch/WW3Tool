# -*- coding: utf-8 -*-
"""Parse RECT grid geometry from WW3 grid description (grid.nml or legacy ASCII)."""
from __future__ import annotations


def parse_rect_flat_meta(lines: list[str]) -> dict | None:
    """Flat ``grid.meta`` (GRID%/RECT% lines, no ``&`` namelist blocks)."""
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
    if "=" not in line:
        return ""
    rhs = line.split("=", 1)[1].strip()
    if "!" in rhs:
        rhs = rhs.split("!", 1)[0].strip()
    return rhs.split()[0].strip("'\"") if rhs else ""


def parse_rect_from_namelist(lines: list[str]) -> dict | None:
    """Parse &RECT_NML ... / block; returns nx, ny, sx, sy, x0, y0 (degrees)."""
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
    """Legacy 5-record ASCII (first data line 'RECT' T 'NONE' style block)."""
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
        "nx": nx,
        "ny": ny,
        "sx": sx_deg,
        "sy": sy_deg,
        "x0": x0,
        "y0": y0,
        "sf": sf,
        "sf0": sf0,
    }


# Keys copied into ww3_grid.nml during Step 4 (flat or full &..._NML meta); all others ignored.
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
    """
    Read grid.meta (or grid description file) and extract only the parameters
    that Step 4 writes into ww3_grid.nml.

    Works for flat ``KEY = value`` lines and for the same keys inside Fortran-style blocks.
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


def rect_lon_lat_mesh(path: str):
    """Return (lon, lat) 2D ndarray mesh in degrees, or (None, None)."""
    import numpy as np

    d = parse_rect_grid_description(path)
    if not d:
        return None, None
    nx, ny = d["nx"], d["ny"]
    lon1d = d["x0"] + np.arange(nx, dtype=float) * d["sx"]
    lat1d = d["y0"] + np.arange(ny, dtype=float) * d["sy"]
    lon, lat = np.meshgrid(lon1d, lat1d)
    return lon, lat
