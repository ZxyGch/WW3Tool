"""
Load mesh settings from INI (config.ini) or JSON (config.json).

When using *.json, output names are always fixed to grid.msh / grid.ww3.
"""

from __future__ import annotations

import configparser
import json
import os
from typing import Any, Dict, Optional

# Defaults for JSON (and fallbacks)
_DEFAULT_SPACING = {
    "hmax": 100.0,
    "hshr": 100.0,
    "hmin": 100.0,
    "nwav": 400,
    "dhdx": 0.05,
}
_DEFAULT_MESH_SETTINGS = {
    "hfun_hmax": 100.0,
}
_DEFAULT_DATA = {
    "dem_file": "RTopo_2_0_4_GEBCO_v2024_60sec_pixel.nc",
    "mask_file": "",
}
_DEFAULT_CMD = {
    "black_sea": 3,
}
_DEFAULT_REGIONAL = {
    "margin_deg": 1.0,
    "edge_segments": 48,
}

FIXED_MESH_FILE = "grid.msh"
FIXED_WW3_MESH_FILE = "grid.ww3"


def _merge_dict(base: dict, override: Optional[dict]) -> dict:
    out = dict(base)
    if override:
        out.update({k: v for k, v in override.items() if v is not None})
    return out


def _flat_from_parts(
    spacing: dict,
    mesh_settings: dict,
    data: dict,
    cmd: dict,
    *,
    fix_output_names: bool,
) -> Dict[str, Any]:
    if fix_output_names:
        mesh_file = FIXED_MESH_FILE
        ww3 = FIXED_WW3_MESH_FILE
    else:
        mesh_file = mesh_settings.get("mesh_file") or FIXED_MESH_FILE
        ww3 = mesh_settings.get("ww3_mesh_file") or FIXED_WW3_MESH_FILE
    return {
        "mesh_file": mesh_file,
        "ww3_mesh_file": ww3,
        "hfun_hmax": float(mesh_settings["hfun_hmax"]),
        "black_sea": int(cmd["black_sea"]),
        "mask_file": (data.get("mask_file") or "").strip(),
        "hmax": float(spacing["hmax"]),
        "hshr": float(spacing["hshr"]),
        "hmin": float(spacing["hmin"]),
        "nwav": int(spacing["nwav"]),
        "dhdx": float(spacing["dhdx"]),
        "dem_file": str(data["dem_file"]),
    }


def _load_json_raw(raw: dict, *, fix_output_names: bool) -> Dict[str, Any]:
    spacing = _merge_dict(_DEFAULT_SPACING, raw.get("spacing"))
    mesh_s = _merge_dict(_DEFAULT_MESH_SETTINGS, raw.get("mesh_settings"))
    data = _merge_dict(_DEFAULT_DATA, raw.get("data"))
    cmd = _merge_dict(_DEFAULT_CMD, raw.get("command_line_args"))
    return _flat_from_parts(spacing, mesh_s, data, cmd, fix_output_names=fix_output_names)


def _from_ini(path: str) -> Dict[str, Any]:
    config = configparser.ConfigParser()
    read_ok = config.read(path)
    if not read_ok:
        raise FileNotFoundError(f"Cannot read config: {path}")
    return {
        "mesh_file": config.get("MeshSettings", "mesh_file", fallback=""),
        "ww3_mesh_file": config.get("MeshSettings", "WW3_mesh_file", fallback=""),
        "hfun_hmax": float(config.get("MeshSettings", "hfun_hmax", fallback="100")),
        "black_sea": config.getint("CommandLineArgs", "black_sea", fallback=3),
        "mask_file": config.get("CommandLineArgs", "mask_file", fallback=""),
        "hmax": float(config.get("Spacing", "hmax", fallback="100.0")),
        "hshr": float(config.get("Spacing", "hshr", fallback="100")),
        "nwav": int(config.get("Spacing", "nwav", fallback="400")),
        "hmin": float(config.get("Spacing", "hmin", fallback="100.0")),
        "dhdx": float(config.get("Spacing", "dhdx", fallback="0.05")),
        "dem_file": config.get("DataFiles", "dem_file", fallback=""),
    }


def load_config(path: str) -> Dict[str, Any]:
    """
    Settings for ocn_ww3.py (global mesh).

    Supports *.ini (legacy) and *.json. JSON always writes grid.msh / grid.ww3.
    """
    path = os.path.expanduser(path)
    if path.lower().endswith(".json"):
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        return _load_json_raw(raw, fix_output_names=True)
    return _from_ini(path)


def load_regional_config(path: str) -> Dict[str, Any]:
    """
    Settings for ocn_ww3_regional.py: base mesh keys + regional box.

    INI: requires [Regional] section.
    JSON: requires non-null \"regional\" object.
    """
    path = os.path.expanduser(path)
    if path.lower().endswith(".json"):
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        reg_in = raw.get("regional")
        if not isinstance(reg_in, dict):
            raise ValueError(
                'config.json for ocn_ww3_regional.py must set '
                '"regional": { "lon_min": ..., ... } (object, not null).'
            )
        for k in ("lon_min", "lon_max", "lat_min", "lat_max", "stereo_lon", "stereo_lat"):
            if k not in reg_in:
                raise ValueError(f'config.json "regional" missing required key: {k}')
        reg = {
            "lon_min": float(reg_in["lon_min"]),
            "lon_max": float(reg_in["lon_max"]),
            "lat_min": float(reg_in["lat_min"]),
            "lat_max": float(reg_in["lat_max"]),
            "margin_deg": float(
                reg_in.get("margin_deg", _DEFAULT_REGIONAL["margin_deg"])
            ),
            "edge_segments": int(
                reg_in.get("edge_segments", _DEFAULT_REGIONAL["edge_segments"])
            ),
            "stereo_lon": float(reg_in["stereo_lon"]),
            "stereo_lat": float(reg_in["stereo_lat"]),
        }
        base = _load_json_raw(raw, fix_output_names=True)
        return {**base, **reg}

    cfg = configparser.ConfigParser()
    read_ok = cfg.read(path)
    if not read_ok:
        raise FileNotFoundError(f"Cannot read config: {path}")
    base = _from_ini(path)
    reg = {
        "lon_min": cfg.getfloat("Regional", "lon_min"),
        "lon_max": cfg.getfloat("Regional", "lon_max"),
        "lat_min": cfg.getfloat("Regional", "lat_min"),
        "lat_max": cfg.getfloat("Regional", "lat_max"),
        "margin_deg": cfg.getfloat("Regional", "margin_deg", fallback=1.0),
        "edge_segments": cfg.getint("Regional", "edge_segments", fallback=48),
        "stereo_lon": cfg.getfloat("Regional", "stereo_lon"),
        "stereo_lat": cfg.getfloat("Regional", "stereo_lat"),
    }
    return {**base, **reg}
