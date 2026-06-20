"""WW3Tool 运行时配置与路径常量。

本模块管理根目录 ``params.yml`` 中 ``desktop:`` 段的加载/保存，以及桌面端与 CLI
共用的路径解析（项目根、网格生成器、默认工作目录、Step 1 强迫场目录等）。

``desktop:`` 段仅保留应用级 UI 设置（语言、主题、最近工作目录等）。
项目参数（网格、WW3、SLURM、服务器等）由 ``params.yml`` 的其它顶层段管理。
"""
import copy
import json
import os
import re
import shutil


# ==================== 配置文件路径设置 ====================
# 获取当前脚本所在目录的绝对路径
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(BASE_DIR)))

# 公共目录路径，用于存储配置文件和公共资源（在项目根目录下）
PUBLIC_DIR = os.path.join(PROJECT_ROOT, "public")

# 确保公共目录存在，如果不存在则创建
os.makedirs(PUBLIC_DIR, exist_ok=True)

# 根目录 params.yml 路径（desktop 段的持久化文件）
PARAMS_FILE = os.path.join(PROJECT_ROOT, "params.yml")

# desktop: 段 YAML 键名 ↔ 旧 config.json 扁平键名（双向映射，兼容消费者 API）
_DESKTOP_YAML_TO_LEGACY = {
    "language": "LANGUAGE",
    "theme": "THEME",
    "run_mode": "RUN_MODE",
    "recent_workdirs": "RECENT_WORKDIRS",
    "forcing_field_dir": "FORCING_FIELD_DIR_PATH",
}
_DESKTOP_LEGACY_TO_YAML = {v: k for k, v in _DESKTOP_YAML_TO_LEGACY.items()}

# 设置页管线参数：扁平键名 → params.yml 嵌套路径（供 settings 视图模型读写）
# 根 params.yml 是基础模板，设置页直接读写顶层路径；CLI/GUI 必须先复制到工作目录再操作
_SETTINGS_KEY_TO_YAML_PATH = {
    "DX": "grid.outer.dx",
    "DY": "grid.outer.dy",
    "NESTED_OUTER_DX": "grid.outer.dx",
    "NESTED_OUTER_DY": "grid.outer.dy",
    "GRIDGEN_VERSION": "grid.gridgen_version",
    "REFERENCE_DATA_PATH": "grid.reference_data_path",
    "NESTED_CONTRACTION_COEFFICIENT": "grid.nested_contraction_coefficient",
    "BATHYMETRY": "grid.structured.bathymetry",
    "COASTLINE_PRECISION": "grid.structured.coastline_precision",
    "MIN_DIST": "grid.structured.min_dist",
    "CUT_OFF": "grid.structured.cut_off",
    "LIM_BATHY": "grid.structured.lim_bathy",
    "LIM_VAL": "grid.structured.lim_val",
    "SPLIT_LIM": "grid.structured.split_lim",
    "LAKE_TOL": "grid.structured.lake_tol",
    "WW3_VERSION": "ww3.version",
    "COMPUTE_PRECISION": "ww3.compute_precision",
    "OUTPUT_PRECISION": "ww3.output_precision",
    "FILE_SPLIT": "ww3.file_split",
    "FREQ_INC": "ww3_grid.SPECTRUM%XFR",
    "FREQ_START": "ww3_grid.SPECTRUM%FREQ1",
    "FREQ_NUM": "ww3_grid.SPECTRUM%NK",
    "DIR_NUM": "ww3_grid.SPECTRUM%NTH",
    "DTMAX": "ww3_grid.TIMESTEPS%DTMAX",
    "DTXY": "ww3_grid.TIMESTEPS%DTXY",
    "DTKTH": "ww3_grid.TIMESTEPS%DTKTH",
    "DTMIN": "ww3_grid.TIMESTEPS%DTMIN",
    "KERNEL_NUM": "slurm.cores",
    "NODE_NUM": "slurm.nodes",
    "DEFAULT_CPU": "slurm.cpu",
    "CPU_GROUP": "slurm.cpu_group",
    "SERVER_HOST": "server.host",
    "SERVER_PORT": "server.port",
    "SERVER_USER": "server.user",
    "SERVER_PASSWORD": "server.password",
    "SERVER_KEY_FILE": "server.key_file",
    "SERVER_SSH_CONFIG_HOST": "server.ssh_config_host",
    "SERVER_PATH": "server.default_remote_dir",
    "MATLAB_PATH": "paths.matlab_path",
    "WW3BIN_PATH": "paths.ww3bin_path",
    "JASON_PATH": "paths.jason_path",
    "NDBC_PATH": "paths.ndbc_path",
}

DEFAULT_OUTPUT_VARS_SCHEME_NAME = "Default"
LEGACY_DEFAULT_OUTPUT_VARS_SCHEME_NAMES = ("默认方案", "Default Scheme")
DEFAULT_OUTPUT_VARS_SCHEME_VARS = [
    "HS",
    "DIR",
    "FP",
    "T02",
    "WND",
    "PHS",
    "PTP",
    "PDIR",
    "PWS",
    "PNR",
    "TWS",
]


def get_project_root():
    """返回 WW3Tool 项目根目录绝对路径。

    由本文件所在位置向上推导，不读取配置文件。
    """
    return PROJECT_ROOT


def get_project_meshgen_path():
    """返回 meshgen 根目录（固定为项目根下子目录）。

    该目录汇集结构化/SMC/非结构三类网格生成后端及其 reference_data、cache。
    不从 ``config.json`` 或环境变量覆盖，保证网格工具版本与仓库一致。
    """
    return os.path.normpath(os.path.join(PROJECT_ROOT, "meshgen"))


# 非结构网格：设置页与 Step2 使用的「扁平」键（与 grid.json 互转）；持久化仅使用 unstructured_generator/grid.json
UNST_MSH_GEN_CONFIG_DEFAULTS = {
    "spacing": {
        "hmax": 100.0,
        "hshr": 20.0,
        "hmin": 2.0,
        "nwav": 400,
        "dhdx": 0.05,
        "deep_ocean_threshold_m": 4000.0,
    },
    "mesh_settings": {"hfun_hmax": 100.0},
    "data": {
        "dem_file": "../reference_data/RTopo_2_0_4_GEBCO_v2024_60sec_pixel.nc",
        "mask_file": "",
    },
    "command_line_args": {"black_sea": 3},
    "regional": {
        "lon_min": 110.0,
        "lon_max": 130.0,
        "lat_min": 10.0,
        "lat_max": 30.0,
        "margin_deg": 1.0,
        "edge_segments": 64,
        "stereo_lon": 120.0,
        "stereo_lat": 20.0,
    },
}

UNSTRUCTURED_GRID_SCALING_DEFAULTS = {
    "upper_bound": 50,
    "middle_bound": -20,
    "lower_bound": -90,
    "scale_north": 9,
    "scale_middle": 20,
    "scale_south_upper": 30,
    "scale_south_lower": 9,
}


def get_unstructured_grid_json_path():
    return os.path.normpath(
        os.path.join(get_project_meshgen_path(), "unstructured_generator", "grid.json")
    )


def get_unst_msh_gen_config_path():
    """兼容旧名：非结构网格统一使用 unstructured_generator/grid.json。"""
    return get_unstructured_grid_json_path()


def default_unst_dem_file_relpath():
    """reference_data 中 RTopo DEM 的相对路径，相对于 unstructured_generator/（与 grid.json 同目录）。"""
    g = get_project_meshgen_path()
    ug = os.path.normpath(os.path.join(g, "unstructured_generator"))
    dem_abs = os.path.join(g, "reference_data", "RTopo_2_0_4_GEBCO_v2024_60sec_pixel.nc")
    try:
        return os.path.relpath(dem_abs, ug).replace("\\", "/")
    except ValueError:
        return UNST_MSH_GEN_CONFIG_DEFAULTS["data"]["dem_file"]


def _grid_json_to_legacy(gj: dict) -> dict:
    d0 = UNST_MSH_GEN_CONFIG_DEFAULTS
    sp = gj.get("Spacing") or {}
    ms = gj.get("MeshSettings") or {}
    df = gj.get("DataFiles") or {}
    cmd = gj.get("CommandLineArgs") or {}
    reg_in = dict(gj.get("Regional") or {})
    dom = gj.get("Domain") or {}
    legacy_reg = copy.deepcopy(d0["regional"])
    if reg_in:
        for k, v in reg_in.items():
            if v is None or k not in legacy_reg:
                continue
            try:
                if k == "edge_segments":
                    legacy_reg[k] = int(v)
                else:
                    legacy_reg[k] = float(v)
            except (TypeError, ValueError):
                pass
    elif dom:
        try:
            legacy_reg["lon_min"] = float(dom.get("west_lon", legacy_reg["lon_min"]))
            legacy_reg["lon_max"] = float(dom.get("east_lon", legacy_reg["lon_max"]))
            legacy_reg["lat_min"] = float(dom.get("south_lat", legacy_reg["lat_min"]))
            legacy_reg["lat_max"] = float(dom.get("north_lat", legacy_reg["lat_max"]))
        except (TypeError, ValueError):
            pass
    mask = str(df.get("mask_file") or cmd.get("mask_file") or "").strip()
    return {
        "spacing": {
            "hmax": float(sp.get("hmax", d0["spacing"]["hmax"])),
            "hshr": float(sp.get("hshr", d0["spacing"]["hshr"])),
            "hmin": float(sp.get("hmin", sp.get("hshr", d0["spacing"]["hmin"]))),
            "nwav": int(sp.get("nwav", d0["spacing"]["nwav"])),
            "dhdx": float(sp.get("dhdx", d0["spacing"]["dhdx"])),
            "deep_ocean_threshold_m": float(
                sp.get("deep_ocean_threshold_m", d0["spacing"]["deep_ocean_threshold_m"])
            ),
        },
        "mesh_settings": {
            "hfun_hmax": float(ms.get("hfun_hmax", d0["mesh_settings"]["hfun_hmax"])),
        },
        "data": {
            "dem_file": str(df.get("dem_file", "") or "").strip(),
            "mask_file": mask,
        },
        "command_line_args": {
            "black_sea": int(cmd.get("black_sea", d0["command_line_args"]["black_sea"])),
        },
        "regional": legacy_reg,
    }


def _legacy_dict_to_grid_json(leg: dict) -> dict:
    sp = leg.get("spacing") or {}
    ms = leg.get("mesh_settings") or {}
    data = leg.get("data") or {}
    cmd = leg.get("command_line_args") or {}
    reg = leg.get("regional") or UNST_MSH_GEN_CONFIG_DEFAULTS["regional"]
    dem = str(data.get("dem_file", "") or "").strip()
    if not dem:
        dem = default_unst_dem_file_relpath()
    mask = str(data.get("mask_file") or cmd.get("mask_file") or "").strip()
    return {
        "Domain": {
            "clip_to_bounds": False,
            "west_lon": float(reg["lon_min"]),
            "east_lon": float(reg["lon_max"]),
            "south_lat": float(reg["lat_min"]),
            "north_lat": float(reg["lat_max"]),
        },
        "Zoom": {
            "zoom_auto_center": True,
            "zoom_lon_deg": 30.5,
            "zoom_lat_deg": 41.5,
        },
        "Workflow": {
            "run_window_mask": False,
            "unst_msh_gen_dir": "unst_msh_gen",
            "resolved_config_name": ".grid_run.ini",
            "jigsaw_python_root": "jigsaw-python",
        },
        "Output": {
            "mesh_workspace_dir": "unst_msh_gen/mesh_workspace",
            "ww3_publish_dir": "output",
            "ww3_publish_basename": "grid.ww3",
        },
        "Spacing": {
            "hmax": float(sp.get("hmax", 100.0)),
            "hshr": float(sp.get("hshr", 20.0)),
            "nwav": int(sp.get("nwav", 400)),
            "hmin": float(sp.get("hmin", sp.get("hshr", 20.0))),
            "dhdx": float(sp.get("dhdx", 0.05)),
            "deep_ocean_threshold_m": float(sp.get("deep_ocean_threshold_m", 4000.0)),
        },
        "ScalingSettings": copy.deepcopy(UNSTRUCTURED_GRID_SCALING_DEFAULTS),
        "MeshSettings": {
            "hfun_hmax": float(ms.get("hfun_hmax", 100.0)),
            "mesh_file": "grid.msh",
            "ww3_mesh_file": "grid.ww3",
        },
        "CommandLineArgs": {
            "black_sea": int(cmd.get("black_sea", 3)),
            "mask_file": mask,
        },
        "DataFiles": {"dem_file": dem},
    }


def _apply_legacy_updates_to_grid_json(full: dict, updates: dict) -> None:
    if not updates:
        return
    if "spacing" in updates and updates["spacing"]:
        full.setdefault("Spacing", {})
        u = updates["spacing"]
        for k in ("hmax", "hshr", "hmin", "dhdx", "deep_ocean_threshold_m"):
            if k in u:
                full["Spacing"][k] = float(u[k])
        if "nwav" in u:
            full["Spacing"]["nwav"] = int(u["nwav"])
    if "mesh_settings" in updates and updates["mesh_settings"]:
        full.setdefault("MeshSettings", {})
        for k, v in updates["mesh_settings"].items():
            full["MeshSettings"][k] = float(v) if k == "hfun_hmax" else v
    if "data" in updates and updates["data"]:
        full.setdefault("DataFiles", {})
        for k, v in updates["data"].items():
            if v is not None:
                full["DataFiles"][k] = v
    if "command_line_args" in updates and updates["command_line_args"]:
        full.setdefault("CommandLineArgs", {})
        full["CommandLineArgs"].update(updates["command_line_args"])
    if "regional" in updates and updates["regional"]:
        full.setdefault("Regional", {})
        for k, v in updates["regional"].items():
            if k in ("lon_min", "lon_max", "lat_min", "lat_max"):
                continue
            if k == "edge_segments":
                full["Regional"][k] = int(v)
            else:
                full["Regional"][k] = float(v) if v is not None else v


def _deep_merge_unst_dict(base, override):
    for k, v in override.items():
        if k in base and isinstance(base[k], dict) and isinstance(v, dict):
            _deep_merge_unst_dict(base[k], v)
        else:
            base[k] = v


def load_unst_msh_gen_config():
    """读取 unstructured_generator/grid.json，转为与旧版一致的 spacing/mesh_settings/data/regional 扁平结构。"""
    data = copy.deepcopy(UNST_MSH_GEN_CONFIG_DEFAULTS)
    data["data"] = dict(data.get("data") or {})
    path = get_unstructured_grid_json_path()
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                gj = json.load(f)
            if isinstance(gj, dict):
                user = _grid_json_to_legacy(gj)
                _deep_merge_unst_dict(data, user)
        except Exception:
            pass
    if not str((data.get("data") or {}).get("dem_file") or "").strip():
        data["data"]["dem_file"] = default_unst_dem_file_relpath()
    return data


def save_unst_msh_gen_config(updates):
    """将 updates 合并写入 unstructured_generator/grid.json（不改动 Domain/Regional 中的经纬度边角）。"""
    path = get_unstructured_grid_json_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)

    def _fresh_full_from_defaults():
        b = copy.deepcopy(UNST_MSH_GEN_CONFIG_DEFAULTS)
        b["data"] = dict(b.get("data") or {})
        b["data"]["dem_file"] = default_unst_dem_file_relpath()
        return _legacy_dict_to_grid_json(b)

    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                full = json.load(f)
            if not isinstance(full, dict):
                full = _fresh_full_from_defaults()
        except Exception:
            full = _fresh_full_from_defaults()
    else:
        full = _fresh_full_from_defaults()
    _apply_legacy_updates_to_grid_json(full, updates)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(full, f, indent=2, ensure_ascii=False)
        f.write("\n")


# SMC 网格：smc_generator/grid.json 默认值（与仓库内模板一致；设置页读写该文件）
SMC_GRID_JSON_DEFAULTS = {
    "input": {
        "bathymetry_file": "../reference_data/etopo2.nc",
        "lon_var": None,
        "lat_var": None,
        "bathy_var": None,
        "bathy_convention": "elevation",
        "auto_flip_lat": True,
        "auto_flip_lon": True,
        "coord_spacing_rtol": 0.001,
        "coord_spacing_atol": 1e-08,
        "nan_fill_value": 1000.0,
    },
    "grid": {
        "name": "grid",
        "n_levels": 2,
        "global": False,
        "arctic": False,
        "glb_arc_lat": 84.4,
        "origin": {"lon0": 0.0, "lat0": -90.0},
        "regional_bounds": {
            "west_lon": 110.0,
            "south_lat": 10.0,
            "east_lon": 130.0,
            "north_lat": 30.0,
        },
    },
    "physics": {"wlevel": 0.0, "depmin": 0.0, "dshalw": -150.0},
    "boundary": {"generate_boundary_cells": True, "msea": 1},
    "output": {"output_dir": "./output", "file_prefix": ""},
}

# SMC 水深：仅使用 reference_data 中三份 NetCDF；grid.json 内存相对 smc_generator 的路径
SMC_REFERENCE_BATHY_FILES = ("etopo1.nc", "etopo2.nc", "gebco.nc")


def smc_bathymetry_relpath_for_combo_index(index: int) -> str:
    """返回相对 smc_generator/ 的路径，如 ../reference_data/etopo2.nc。"""
    i = max(0, min(int(index), len(SMC_REFERENCE_BATHY_FILES) - 1))
    return f"../reference_data/{SMC_REFERENCE_BATHY_FILES[i]}"


def smc_bathymetry_combo_index_from_path(bathy_value) -> int:
    """从已有 bathymetry_file 推断设置页下拉索引：0=ETOPO1，1=ETOPO2，2=GEBCO。"""
    s = str(bathy_value or "").replace("\\", "/").lower()
    if "etopo1" in s:
        return 0
    if "gebco" in s:
        return 2
    return 1


def get_smc_grid_json_path():
    """meshgen/smc_generator/grid.json 绝对路径。"""
    return os.path.normpath(
        os.path.join(get_project_meshgen_path(), "smc_generator", "grid.json")
    )


def _deep_merge_smc_dict(base, override):
    for k, v in override.items():
        if k in base and isinstance(base[k], dict) and isinstance(v, dict) and v:
            _deep_merge_smc_dict(base[k], v)
        else:
            base[k] = copy.deepcopy(v)


def load_smc_grid_json_for_settings():
    """读取 smc_generator/grid.json，与 SMC_GRID_JSON_DEFAULTS 深度合并（用于设置页展示）。"""
    data = copy.deepcopy(SMC_GRID_JSON_DEFAULTS)
    path = get_smc_grid_json_path()
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                user = json.load(f)
            if isinstance(user, dict):
                _deep_merge_smc_dict(data, user)
        except Exception:
            pass
    return data


def save_smc_grid_json_updates(updates: dict):
    """将嵌套 updates 合并写入 smc_generator/grid.json（保留文件中未出现在 updates 的其它键）。"""
    path = get_smc_grid_json_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                full = json.load(f)
            if not isinstance(full, dict):
                full = copy.deepcopy(SMC_GRID_JSON_DEFAULTS)
        except Exception:
            full = copy.deepcopy(SMC_GRID_JSON_DEFAULTS)
    else:
        full = copy.deepcopy(SMC_GRID_JSON_DEFAULTS)
    _deep_merge_smc_dict(full, updates)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(full, f, indent=2, ensure_ascii=False)
        f.write("\n")


# ==================== 默认配置值 ====================
# 仅保留结构性回退（params.yml desktop: 段缺失时的最低保障）。
# 所有有意义的默认值由 params.yml 提供，此处不放具体配置值。
DEFAULT_CONFIG = {
    "DEFAULT_WORKDIR": os.path.join(PROJECT_ROOT, "workSpace"),
    "RECENT_WORKDIRS": [],
}


WW3_VERSION_VALUES = ("6.07", "7.14")


def _nml_template_dir(version: str) -> str:
    """返回指定版本的 NML 模板目录绝对路径（如 ``public/6.07_nml``）。"""
    return os.path.join(PUBLIC_DIR, f"{version}_nml")


def get_nml_template_dir() -> str:
    """返回当前 params.yml 中 ``ww3.version`` 对应的 NML 模板目录。"""
    return _nml_template_dir(get_ww3_version())


def get_ww3_version() -> str:
    """从 params.yml 读取当前 WW3 版本，默认 '6.07'。"""
    root = _read_root_params()
    ww3 = root.get("ww3") or {}
    return str(ww3.get("version", "6.07"))


def swap_ww3_version(new_version: str) -> bool:
    """切换 WW3 版本：更新 params.yml 中的 ``ww3.version``。

    模板目录使用固定命名 ``public/{version}_nml``，无需重命名。
    """
    if new_version not in WW3_VERSION_VALUES:
        return False

    old_version = get_ww3_version()
    if old_version == new_version:
        return True

    target_dir = _nml_template_dir(new_version)
    if not os.path.isdir(target_dir):
        print(f"切换 WW3 版本失败：模板目录 {target_dir} 不存在")
        return False

    root = _read_root_params()
    ww3 = root.get("ww3") or {}
    ww3["version"] = new_version
    root["ww3"] = ww3
    return _write_root_params(root)


RUN_MODE_VALUES = ("local", "server", "both")

# Legacy RUN_MODE strings (display labels or old saves) → canonical codes.
_RUN_MODE_ALIASES = {
    "local": "local",
    "server": "server",
    "both": "both",
    "local run": "local",
    "server run": "server",
    "local + server run": "both",
    "local+server run": "both",
    "local+server": "both",
    "本地运行": "local",
    "服务器运行": "server",
    "本地+服务器运行": "both",
}


def normalize_run_mode(value: object, *, default: str = "both") -> str:
    """Normalize ``RUN_MODE`` to ``local`` / ``server`` / ``both``."""
    if value is None:
        return default
    raw = str(value).strip()
    if not raw:
        return default
    if raw in _RUN_MODE_ALIASES:
        return _RUN_MODE_ALIASES[raw]
    folded = raw.casefold()
    if folded in _RUN_MODE_ALIASES:
        return _RUN_MODE_ALIASES[folded]
    return default


def normalize_output_vars_schemes(config):
    """Normalize spectral partition scheme names to the canonical English default."""
    if not isinstance(config, dict):
        return False

    schemes = config.get("OUTPUT_VARS_SCHEMES", {})
    if not isinstance(schemes, dict):
        schemes = {}
        config["OUTPUT_VARS_SCHEMES"] = schemes
        changed = True
    else:
        changed = False

    default_name = DEFAULT_OUTPUT_VARS_SCHEME_NAME
    default_vars = list(DEFAULT_OUTPUT_VARS_SCHEME_VARS)
    current_default_vars = schemes.get(default_name)

    for legacy_name in LEGACY_DEFAULT_OUTPUT_VARS_SCHEME_NAMES:
        legacy_vars = schemes.get(legacy_name)
        if legacy_vars is None:
            continue

        if current_default_vars is None:
            schemes[default_name] = legacy_vars
            current_default_vars = legacy_vars
            changed = True
        elif current_default_vars == default_vars and legacy_vars:
            schemes[default_name] = legacy_vars
            current_default_vars = legacy_vars
            changed = True

        del schemes[legacy_name]
        changed = True

    if default_name not in schemes:
        schemes[default_name] = default_vars
        changed = True

    return changed


def _load_yaml():
    """延迟导入 PyYAML（避免 CLI 无 yaml 依赖时崩溃）。"""
    import yaml
    return yaml


# ── YAML comment injection ─────────────────────────────────────────────────
# PyYAML's safe_dump strips comments; this table maps YAML line prefixes
# (top-level or indented section headers) to inline documentation that will
# be re-injected after every dump so user annotations survive round-trips.

_YAML_COMMENTS: list[tuple[str, str]] = [
    # ── top-level sections ──────────────────────────────────────────────
    ("presets:",
     "# ────────────────────────────────────────────────────────────────────\n"
     "# Preset definitions: reusable named lists that are referenced by name\n"
     "# in other sections. Avoids duplicating long lists across configs.\n"
     "#\n"
     "#   output_scheme  – named lists of WW3 output field abbreviations.\n"
     "#     'standard'      : essential wave parameters (HS, DIR, FP, T02 …).\n"
     "#     'with_spectrum'  : standard + 2-D energy density (EF).\n"
     "#     'all_fields'     : every available WW3 output variable.\n"
     "#   server_st           – server WW3 binary paths keyed by scheme name\n"
     "#                          (ST2 / ST4 / ST6 / ST6A / ST6B).\n"
     "#   local_st           – local WW3 binary paths keyed by scheme name\n"
     "#                          (used by local run panel).\n"
     "#   structured_bathymetry – bathymetry datasets available for structured grids\n"
     "#                          (GEBCO / ETOPO1 / ETOPO2).\n"
     "#   smc_bathymetry      – bathymetry datasets for SMC grids.\n"
     "#   coastline_precision – GSHHG coastline resolution levels\n"
     "#                          (full > high > inter > low > coarse).\n"
     "#   file_split          – output file splitting strategies\n"
     "#                          (none / hour / day / month / year).\n"
     "# ────────────────────────────────────────────────────────────────────"),
    ("workdir:",
     "# ────────────────────────────────────────────────────────────────────\n"
     "# Working directory: all intermediate files, WW3 namelists, forcing\n"
     "# inputs, model output and post-processing results are stored here.\n"
     "#   path – absolute or relative path to the work directory.\n"
     "# ────────────────────────────────────────────────────────────────────"),
    ("forcing:",
     "# ────────────────────────────────────────────────────────────────────\n"
     "# Forcing fields: NetCDF file paths for external driving fields.\n"
     "#   wind    – 10-m wind speed / direction (U10, V10).\n"
     "#   current – ocean surface current (UCUR, VCUR).\n"
     "#   level   – sea-surface elevation anomaly (LEV).\n"
     "#   ice     – sea-ice concentration (IC1 / IC5).\n"
     "#   process_mode     – 'copy' duplicates files into workdir;\n"
     "#                      'move' relocates the originals.\n"
     "#   auto_associate   – when true, automatically match dropped / selected\n"
     "#                      files to forcing variables by filename keyword.\n"
     "# ────────────────────────────────────────────────────────────────────"),
    ("grid:",
     "# ────────────────────────────────────────────────────────────────────\n"
     "# Grid generation settings (structured / SMC / unstructured).\n"
     "#   mesh_type – grid topology: 'structured' | 'smc' | 'unstructured'.\n"
     "#   grid_type – 'normal' (single domain) or 'nested' (two-level\n"
     "#               refinement with inner high-resolution patch).\n"
     "#   gridgen_version – grid generator back-end ('Python' or 'MATLAB').\n"
     "#   reference_data_path – path to bathymetry / coastline data bundle;\n"
     "#                          null = auto-detect from project defaults.\n"
     "#   nested_contraction_coefficient – size ratio between outer and\n"
     "#                          inner grid cells for nested grids (≥ 1).\n"
     "#   outer     – outer (or only) grid domain definition:\n"
     "#     dx / dy – cell size in degrees (structured) or base spacing.\n"
     "#     lon     – [west, east] longitude bounds in degrees.\n"
     "#     lat     – [south, north] latitude bounds in degrees.\n"
     "# ────────────────────────────────────────────────────────────────────"),
    ("  structured:",
     "  # Structured grid options:\n"
     "  #   bathymetry       – bathymetry dataset name (see presets.structured_bathymetry).\n"
     "  #   coastline_precision – GSHHG coastline detail level (full/high/inter/low/coarse).\n"
     "  #   min_dist         – minimum distance filter between adjacent grid points (km).\n"
     "  #   cut_off          – land-sea mask cut-off: 0 = keep all sea points.\n"
     "  #   lim_bathy        – depth-based cell inclusion threshold (fraction of cell wet).\n"
     "  #   lim_val          – masking threshold for cell classification (0–1).\n"
     "  #   split_lim        – split-cell limit: 0 = disabled.\n"
     "  #   lake_tol         – minimum lake area (cells) to keep; smaller lakes are filled."),
    ("  smc:",
     "  # SMC (Spherical Multi-Cell) grid options:\n"
     "  #   bathymetry       – dataset name (see presets.smc_bathymetry).\n"
     "  #   bathy_convention – 'elevation' (positive up) or 'depth' (positive down).\n"
     "  #   n_levels         – number of cell-size refinement levels.\n"
     "  #   wlevel           – water-level reference index.\n"
     "  #   depmin           – minimum depth below which cells are excluded (m).\n"
     "  #   dshalw           – shallow-water depth threshold for extra refinement (m).\n"
     "  #   generate_boundary_cells – whether to create open-boundary ghost cells.\n"
     "  #   msea             – minimum cell count across straits.\n"
     "  #   options.input    – low-level input pre-processing (auto-flip, tolerances).\n"
     "  #   options.grid     – grid identity & projection (global, arctic, origin).\n"
     "  #   options.output   – output file naming and formatting."),
    ("  unstructured:",
     "  # Unstructured (triangular) grid spacing parameters:\n"
     "  #   hmax  – maximum element spacing in deep water (km).\n"
     "  #   hmin  – minimum allowed spacing everywhere (km).\n"
     "  #   hshr  – target spacing near shorelines (km).\n"
     "  #   nwav  – number of wavelengths per element for resolution.\n"
     "  #   dhdx  – rate of spacing change with depth gradient.\n"
     "  #   deep_ocean_threshold_m – depth (m) above which hmax applies.\n"
     "  #   margin_deg       – buffer margin around domain boundary (degrees).\n"
     "  #   edge_segments    – number of segments along coastlines.\n"
     "  #   options.data     – optional mask / exclusion file.\n"
     "  #   options.command_line_args – extra JIGSAW CLI flags.\n"
     "  #   options.regional – stereographic projection centre (stereo_lon/lat)."),
    ("calc:",
     "# ────────────────────────────────────────────────────────────────────\n"
     "# Calculation mode:\n"
     "#   mode – 'region' (gridded output over the full domain) or\n"
     "#          'points' (output at specific locations only).\n"
     "#   points      – list of [name, lon, lat] triples for point output.\n"
     "#   track_points – optional moving-point tracks for Lagrangian output\n"
     "#                  (each entry: list of [time, lon, lat] waypoints).\n"
     "# ────────────────────────────────────────────────────────────────────"),
    ("ww3:",
     "# ────────────────────────────────────────────────────────────────────\n"
     "# WW3 model run settings.\n"
     "#   version           – WW3 version: '6.07' or '7.14'\n"
     "#                          (reads public/{version}_nml template directory).\n"
     "#   start_date / end_date – simulation period (YYYYMMDD).\n"
     "#   compute_precision – main propagation time-step DTMAX (seconds).\n"
     "#   output_precision  – output writing interval (seconds).\n"
     "#   file_split        – output file splitting: none | hour | day | month | year.\n"
     "#   output_scheme     – named preset from presets.output_scheme.\n"
     "#   st                – source-term package (ST2 / ST4 / ST6 / ST6A / ST6B).\n"
     "# ────────────────────────────────────────────────────────────────────"),
    ("ww3_grid:",
     "# ────────────────────────────────────────────────────────────────────\n"
     "# WW3 grid namelist overrides (written into ww3_grid.nml at runtime).\n"
     "# Keys follow the Fortran namelist syntax with '%' as sub-key separator.\n"
     "#\n"
     "# SPECTRUM%XFR   – logarithmic frequency increment ratio (default 1.1).\n"
     "# SPECTRUM%FREQ1 – lowest discrete frequency in Hz.\n"
     "# SPECTRUM%NK    – number of frequency bins.\n"
     "# SPECTRUM%NTH   – number of directional bins.\n"
     "# TIMESTEPS%DTMAX – maximum overall time-step (s).\n"
     "# TIMESTEPS%DTXY  – spatial propagation time-step (s).\n"
     "# TIMESTEPS%DTKTH – directional propagation time-step (s).\n"
     "# TIMESTEPS%DTMIN – minimum (source-term) time-step (s).\n"
     "# ────────────────────────────────────────────────────────────────────"),
    ("slurm:",
     "# ────────────────────────────────────────────────────────────────────\n"
     "# SLURM job-scheduler settings for HPC cluster submissions.\n"
     "#   job_name  – Slurm job name written to #SBATCH -J; null uses workdir name.\n"
     "#   cpu       – default CPU model identifier.\n"
     "#   cpu_group – list of acceptable CPU models for job placement.\n"
     "#   nodes     – number of compute nodes to request.\n"
     "#   cores     – CPU cores per node.\n"
     "# ────────────────────────────────────────────────────────────────────"),
    ("plot:",
     "# ────────────────────────────────────────────────────────────────────\n"
     "# Post-processing and validation plot settings.\n"
     "# Each sub-section is invoked individually via CLI commands:\n"
     "#   plot-wave-maps / plot-spectrum / plot-jason3 / plot-ndbc / plot-wind\n"
     "# ────────────────────────────────────────────────────────────────────"),
    ("  wave_maps:",
     "  # Wave-height filled-colour maps, contour maps, and video.\n"
     "  #   time_step_hours – temporal sampling interval (hours).\n"
     "  #   generate_video  – whether to create an MP4 animation.\n"
     "  #   show_land_coastline – overlay coastline on maps.\n"
     "  #   dpi / figsize   – image resolution and dimensions (null = auto).\n"
     "  #   output_folder   – custom output directory (null = workdir default)."),
    ("  spectrum:",
     "  # 2-D directional spectrum plots at specified station locations.\n"
     "  #   time_step_hours  – temporal sampling interval (hours).\n"
     "  #   energy_threshold – minimum energy density to display.\n"
     "  #   plot_mode        – 'normalized' or 'actual' (null = actual)."),
    ("  jason3:",
     "  # Jason-3 satellite altimeter track matching / validation.\n"
     "  #   data_folder       – local folder containing downloaded Jason-3 files.\n"
     "  #   lon_lat           – [lon_w, lon_e, lat_s, lat_n] matching region.\n"
     "  #   time_range        – [start, end] date strings (YYYYMMDD).\n"
     "  #   max_dist_deg      – maximum spatial mismatch for track matching (degrees).\n"
     "  #   time_window_hours – maximum temporal mismatch window (hours)."),
    ("  ndbc:",
     "  # NDBC buoy observation matching or data download.\n"
     "  #   data_folder – local folder containing NDBC station data files.\n"
     "  #   download    – if true, download station data automatically from NDBC.\n"
     "  #   time_range  – [start, end] date strings (YYYYMMDD)."),
    ("  wind_field:",
     "  # Wind-field filled-colour maps with optional arrow / barb overlays.\n"
     "  #   time_step_hours – temporal sampling interval (null = auto from file).\n"
     "  #   flag_type       – overlay style: 'arrow' / 'barb' / 'none'.\n"
     "  #   flag_density    – spacing between flag glyphs (stride steps)."),
    ("server:",
     "# ────────────────────────────────────────────────────────────────────\n"
     "# Remote server connection settings (SSH / SFTP).\n"
     "#   host / port        – hostname or IP and SSH port number.\n"
     "#   user               – login username.\n"
     "#   password / key_file – password string or path to private key.\n"
     "#   ssh_config_host    – Host alias in ~/.ssh/config (resolved at connect time).\n"
     "#   default_remote_dir – base directory on the remote side; workdir name\n"
     "#                        is appended automatically during submission.\n"
     "#   remote_dir         – full resolved remote path (read-only, auto-set).\n"
     "# ────────────────────────────────────────────────────────────────────"),
    ("paths:",
     "# ────────────────────────────────────────────────────────────────────\n"
     "# External tool and data directory paths.\n"
     "#   matlab_path       – MATLAB executable for grid generators that require it.\n"
     "#   ww3bin_path       – directory containing compiled WW3 binaries.\n"
     "#   jason_path        – local storage directory for Jason-3 satellite data.\n"
     "#   ndbc_path         – local storage directory for NDBC buoy data.\n"
     "#   jason3_download_url – base URL for Jason-3 data downloads from NCEI.\n"
     "# ────────────────────────────────────────────────────────────────────"),
    ("desktop:",
     "# ════════════════════════════════════════════════════════════════════\n"
     "# Desktop-only settings (managed by the Settings page; CLI ignores).\n"
     "#   language           – UI locale: 'en_US' or 'zh_CN'.\n"
     "#   theme              – colour theme: 'LIGHT' / 'DARK' / 'AUTO'.\n"
     "#   run_mode           – 'local' / 'server' / 'both'.\n"
     "#   default_workdir    – default parent folder for new work directories.\n"
     "#   recent_workdirs    – recently opened work directories (MRU list).\n"
     "#   forcing_field_dir  – last-used forcing file browse directory.\n"
     "# ════════════════════════════════════════════════════════════════════"),
]


def _dump_yaml_with_comments(data: dict, yaml_mod=None) -> str:
    """Dump *data* to a YAML string and re-inject documentation comments.

    Uses ``yaml.safe_dump`` for correct serialisation, then walks the output
    line by line, inserting block comments from ``_YAML_COMMENTS`` before the
    first matching line for each entry.

    Args:
        data: The dictionary to serialise.
        yaml_mod: Optional pre-imported yaml module; imported lazily if None.
    """
    if yaml_mod is None:
        yaml_mod = _load_yaml()
    raw_text: str = yaml_mod.safe_dump(
        data, allow_unicode=True, sort_keys=False, default_flow_style=False,
    )
    # Track which comment groups have already been injected (inject once).
    used: set[int] = set()
    out_lines: list[str] = []
    for line in raw_text.splitlines(keepends=True):
        stripped = line.rstrip("\n\r")
        for idx, (prefix, comment) in enumerate(_YAML_COMMENTS):
            if idx in used:
                continue
            # Top-level keys start at column 0; nested keys are indented.
            if prefix.startswith("  "):
                # Indented key: match only when line starts with same indent
                if stripped.startswith(prefix):
                    out_lines.append(comment + "\n")
                    used.add(idx)
                    break
            else:
                if stripped.startswith(prefix):
                    out_lines.append(comment + "\n")
                    used.add(idx)
                    break
        out_lines.append(line)
    return "".join(out_lines)


def _read_root_params() -> dict:
    """读取根目录 params.yml，返回完整字典；文件不存在或解析失败返回空字典。"""
    if not os.path.isfile(PARAMS_FILE):
        return {}
    try:
        yaml = _load_yaml()
        with open(PARAMS_FILE, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_root_params(data: dict) -> bool:
    """将完整字典写回根目录 params.yml，自动注入文档注释。"""
    try:
        text = _dump_yaml_with_comments(data)
        with open(PARAMS_FILE, "w", encoding="utf-8") as f:
            f.write(text)
        return True
    except Exception as e:
        print(f"保存 params.yml 失败: {e}")
        return False


# 根 params.yml 里"必须存在才能用"的本地路径参数（section, key）。
# 不含按需创建的目录（workdir.path / workdir.default_workdir / paths.jason_path /
# paths.ndbc_path）、远程路径（server.*_remote_dir）与 URL。
_ROOT_PATH_PARAMS = (
    ("forcing", "wind"),
    ("forcing", "current"),
    ("forcing", "level"),
    ("forcing", "ice"),
    ("grid", "reference_data_path"),
    ("paths", "matlab_path"),
    ("paths", "ww3bin_path"),
    ("server", "key_file"),
)


def sanitize_root_params_paths() -> list[str]:
    """校验根 params.yml 的本地路径参数；指向不存在路径的一律置为 null。

    仅在 shell/CLI 启动时调用，清理模板里的失效路径（如已移动/删除的强迫场文件）。
    返回被置空的参数名列表（如 ``["forcing.wind"]``）；无改动则不写文件。

    [EN] Validate local path params in the root params.yml; null out any that point
    to a non-existent path. Called on shell/CLI startup. Returns the nulled keys.
    """
    root = _read_root_params()
    nulled: list[str] = []
    for section, key in _ROOT_PATH_PARAMS:
        sec = root.get(section)
        if not isinstance(sec, dict):
            continue
        val = sec.get(key)
        if isinstance(val, str) and val.strip():
            if not os.path.exists(os.path.expanduser(val.strip())):
                sec[key] = None
                nulled.append(f"{section}.{key}")
    if nulled:
        _write_root_params(root)
    return nulled


def _desktop_section_to_legacy(desktop: dict) -> dict:
    """将 desktop: 段 YAML 键名转为旧 config.json 扁平键名。"""
    out = {}
    if not isinstance(desktop, dict):
        return out
    for yaml_key, legacy_key in _DESKTOP_YAML_TO_LEGACY.items():
        if yaml_key in desktop:
            out[legacy_key] = desktop[yaml_key]
    return out


def _legacy_to_desktop_section(legacy: dict) -> dict:
    """将旧 config.json 扁平键名转为 desktop: 段 YAML 键名。"""
    out = {}
    if not isinstance(legacy, dict):
        return out
    for legacy_key, yaml_key in _DESKTOP_LEGACY_TO_YAML.items():
        if legacy_key in legacy:
            out[yaml_key] = legacy[legacy_key]
    return out


def load_config():
    """从根目录 ``params.yml`` 的 ``desktop:`` 段加载配置。

    若 ``desktop:`` 段不存在则返回 ``DEFAULT_CONFIG`` 中的结构性回退值。
    返回扁平字典（键名与旧 ``config.json`` 一致），兼容所有消费者。
    """
    root = _read_root_params()
    desktop_raw = root.get("desktop")

    if isinstance(desktop_raw, dict) and desktop_raw:
        merged = DEFAULT_CONFIG.copy()
        merged.update(_desktop_section_to_legacy(desktop_raw))
        merged["RUN_MODE"] = normalize_run_mode(merged.get("RUN_MODE"))
        return merged

    default_config = DEFAULT_CONFIG.copy()
    default_config["RUN_MODE"] = normalize_run_mode(default_config.get("RUN_MODE"))
    return default_config


def save_config(config):
    """将桌面配置字典持久化到根目录 ``params.yml`` 的 ``desktop:`` 段。

    仅更新 ``desktop:`` 段，保留 params.yml 的其它内容不变。
    返回是否写入成功。
    """
    root = _read_root_params()
    root["desktop"] = _legacy_to_desktop_section(config)
    return _write_root_params(root)


def _get_nested(data: dict, dotted: str):
    """按点号路径读取嵌套字典值；不存在返回 None。"""
    parts = dotted.split(".")
    cur = data
    for part in parts:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
        if cur is None:
            return None
    return cur


def _coerce_yaml_value(value):
    """将字符串形式的数值转为 int/float，避免 YAML 中出现 ``'32'`` 之类的写法。"""
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text:
        return value
    if re.fullmatch(r"[+-]?\d+", text):
        return int(text)
    if re.fullmatch(r"[+-]?(?:\d+\.\d*|\.\d+)(?:[eE][+-]?\d+)?", text) or re.fullmatch(
        r"[+-]?\d+[eE][+-]?\d+", text,
    ):
        return float(text)
    return value


def _set_nested(data: dict, dotted: str, value) -> None:
    """按点号路径写入嵌套字典值（自动创建中间层），并对数值做类型归一化。"""
    parts = dotted.split(".")
    cur = data
    for part in parts[:-1]:
        nxt = cur.get(part)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[part] = nxt
        cur = nxt
    cur[parts[-1]] = _coerce_yaml_value(value)


def load_full_config() -> dict:
    """读取 desktop 段 + 顶层管线参数，返回扁平字典（供设置页使用）。

    根 params.yml 是基础模板，设置页直接读写顶层路径。
    桌面键使用旧名（``LANGUAGE`` 等），管线键使用 ``_SETTINGS_KEY_TO_YAML_PATH`` 中的旧名。
    """
    merged = load_config()
    root = _read_root_params()
    for flat_key, yaml_path in _SETTINGS_KEY_TO_YAML_PATH.items():
        value = _get_nested(root, yaml_path)
        if value is not None:
            merged[flat_key] = value
    # presets 段：输出方案与 ST 版本
    presets = root.get("presets") or {}
    if isinstance(presets.get("output_scheme"), dict):
        merged["OUTPUT_VARS_SCHEMES"] = presets["output_scheme"]
    if isinstance(presets.get("server_st"), dict):
        st_dict = presets["server_st"]
        merged["ST_VERSIONS"] = [{"name": k, "path": v} for k, v in st_dict.items()]
        merged["ST_OPTIONS"] = list(st_dict.keys())
        merged["DEFAULT_ST"] = list(st_dict.keys())[0] if st_dict else ""
    if isinstance(presets.get("local_st"), dict):
        lst_dict = presets["local_st"]
        merged["LOCAL_ST_VERSIONS"] = [{"name": k, "path": v} for k, v in lst_dict.items()]
        merged["LOCAL_ST_OPTIONS"] = list(lst_dict.keys())
        merged["DEFAULT_LOCAL_ST"] = list(lst_dict.keys())[0] if lst_dict else ""
    return merged


def save_full_config(config: dict) -> bool:
    """将扁平字典拆分写入 params.yml：桌面键 → ``desktop:``，管线键 → 顶层路径。

    供设置页 autosave 使用。根 params.yml 是基础模板，设置页直接修改顶层参数。
    """
    root = _read_root_params()
    # 更新 desktop 段的 UI 设置键
    desktop = root.get("desktop") or {}
    desktop.update(_legacy_to_desktop_section(config))
    root["desktop"] = desktop
    # 写入顶层管线参数
    written_paths: set[str] = set()
    for flat_key, yaml_path in _SETTINGS_KEY_TO_YAML_PATH.items():
        if flat_key in config and yaml_path not in written_paths:
            value = config[flat_key]
            if value is not None and str(value).strip() != "":
                _set_nested(root, yaml_path, value)
                written_paths.add(yaml_path)
            elif flat_key in ("SERVER_KEY_FILE", "SERVER_PASSWORD", "SERVER_SSH_CONFIG_HOST"):
                _set_nested(root, yaml_path, None)
                written_paths.add(yaml_path)
    # presets 段
    if "OUTPUT_VARS_SCHEMES" in config:
        root.setdefault("presets", {})["output_scheme"] = config["OUTPUT_VARS_SCHEMES"]
    if "ST_VERSIONS" in config:
        versions = config["ST_VERSIONS"]
        if isinstance(versions, list):
            st_dict = {}
            for item in versions:
                if isinstance(item, dict) and item.get("name"):
                    st_dict[item["name"]] = item.get("path", "")
            root.setdefault("presets", {})["server_st"] = st_dict
    if "LOCAL_ST_VERSIONS" in config:
        versions = config["LOCAL_ST_VERSIONS"]
        if isinstance(versions, list):
            lst_dict = {}
            for item in versions:
                if isinstance(item, dict) and item.get("name"):
                    lst_dict[item["name"]] = item.get("path", "")
            root.setdefault("presets", {})["local_st"] = lst_dict
    return _write_root_params(root)


def _normalize_recent_workdir(workdir):
    if not workdir or not isinstance(workdir, str):
        return ""
    return os.path.abspath(os.path.normpath(os.path.expanduser(workdir.strip())))


def _recent_workdir_key(workdir):
    return os.path.normcase(_normalize_recent_workdir(workdir))


def order_recent_workdirs_for_display(
    paths: list[str],
    *,
    current_folder: str | None = None,
) -> list[str]:
    """整理弹窗展示用的工作目录顺序（最近打开优先，索引 0 显示在最上方）。"""
    ordered: list[str] = []
    seen: set[str] = set()
    for path in paths:
        normalized = _normalize_recent_workdir(path)
        key = _recent_workdir_key(normalized)
        if normalized and key not in seen and os.path.exists(normalized):
            ordered.append(normalized)
            seen.add(key)

    if current_folder:
        current = _normalize_recent_workdir(current_folder)
        if current and os.path.exists(current):
            current_key = _recent_workdir_key(current)
            ordered = [current] + [p for p in ordered if _recent_workdir_key(p) != current_key]

    return ordered


def ensure_project_data_dir(config_key, folder_name):
    """确保指定数据目录存在；若配置为空或路径不存在，则回退到项目根目录下的默认子目录。"""
    project_root = get_project_root()
    default_dir = os.path.normpath(os.path.join(project_root, folder_name))

    config = load_config()
    raw_path = str(config.get(config_key, "") or "").strip()
    target_dir = os.path.normpath(raw_path) if raw_path and os.path.isdir(raw_path) else default_dir

    os.makedirs(target_dir, exist_ok=True)

    if str(config.get(config_key, "") or "").strip() != target_dir:
        config[config_key] = target_dir
        save_config(config)

    return target_dir


def get_forcing_field_default_dir():
    """获取默认的强迫场文件目录（供第一步选场等使用）。"""
    try:
        config = load_config()
        forcing_dir = config.get("FORCING_FIELD_DIR_PATH", "").strip()
        if forcing_dir:
            if not os.path.isabs(forcing_dir):
                # 相对路径相对于项目根目录
                project_root = os.path.dirname(os.path.dirname(BASE_DIR))
                forcing_dir = os.path.join(project_root, forcing_dir)
            forcing_dir = os.path.normpath(forcing_dir)
            if os.path.exists(forcing_dir):
                return forcing_dir
        # 默认目录：项目根目录下的 public/forcing
        default_dir = os.path.join(get_project_root(), "public", "forcing")
        if os.path.exists(default_dir):
            return default_dir
    except Exception:
        pass
    return os.getcwd()

# 加载配置
_config = load_config()

# 全局变量（仅保留应用级设置，项目参数由 params.yml 管理）
# 工具路径（MATLAB_PATH、WW3BIN_PATH 等）已迁移到 params.yml 的 paths: 段。

def reload_config():
    """重新加载配置并更新本模块全局变量。

    在设置页保存或外部修改 ``params.yml`` 后应调用，使模块级缓存与磁盘一致。
    """
    global _config

    _config = load_config()

# 初始化全局变量
reload_config()


def add_recent_workdir(workdir):
    """将工作目录加入 ``RECENT_WORKDIRS`` 最近列表（最多保留 3 条）。

    路径不存在或非字符串时静默忽略；已存在的条目会移到列表首位。
    """
    workdir = _normalize_recent_workdir(workdir)
    if not workdir or not os.path.exists(workdir):
        return

    config = load_config()
    target_key = _recent_workdir_key(workdir)
    recent_dirs = []
    seen = {target_key}
    for path in config.get("RECENT_WORKDIRS", []):
        normalized_path = _normalize_recent_workdir(path)
        key = _recent_workdir_key(normalized_path)
        if (
            normalized_path
            and os.path.exists(normalized_path)
            and key not in seen
        ):
            recent_dirs.append(normalized_path)
            seen.add(key)

    recent_dirs.insert(0, workdir)
    recent_dirs = recent_dirs[:3]

    # 更新配置
    config["RECENT_WORKDIRS"] = recent_dirs
    save_config(config)


def get_recent_workdirs():
    """返回最近打开且仍存在于磁盘的工作目录列表（最多 3 条）。

    会自动从配置中剔除已删除的无效路径。
    """
    config = load_config()
    recent_dirs = config.get("RECENT_WORKDIRS", [])

    # 过滤掉不存在的目录，同时折叠同一目录的不同写法。
    valid_dirs = []
    seen = set()
    for dir_path in recent_dirs:
        normalized_path = _normalize_recent_workdir(dir_path)
        key = _recent_workdir_key(normalized_path)
        if normalized_path and key not in seen and os.path.exists(normalized_path):
            valid_dirs.append(normalized_path)
            seen.add(key)

    valid_dirs = valid_dirs[:3]

    # 更新配置（移除无效目录）
    if valid_dirs != recent_dirs:
        config["RECENT_WORKDIRS"] = valid_dirs
        save_config(config)

    return valid_dirs


def get_default_workdir(create_if_not_exists=True):
    """获取 ``DEFAULT_WORKDIR`` 配置项对应的规范化工作目录路径。

    参数:
        create_if_not_exists: 目录不存在时是否自动创建（默认 True）

    返回:
        成功时为绝对路径字符串；无法创建或配置无效时为 None
    """
    # 从根 params.yml 的 workdir.default_workdir 读取（已从 desktop 段移到 workdir 段）。
    raw = (_read_root_params().get("workdir") or {}).get("default_workdir")
    workdir = str(raw).strip() if raw else ""

    # 如果配置中的路径为空或无效，使用默认值
    if not workdir:
        workdir = DEFAULT_CONFIG.get("DEFAULT_WORKDIR", os.path.join(PROJECT_ROOT, "workSpace"))
    
    # 规范化路径
    workdir = os.path.normpath(workdir.strip())
    
    # 如果目录不存在，尝试创建
    if not os.path.exists(workdir):
        if create_if_not_exists:
            try:
                os.makedirs(workdir, exist_ok=True)
            except Exception as e:
                print(f"无法创建默认工作目录 {workdir}: {e}")
                return None
        else:
            return None
    
    return workdir
