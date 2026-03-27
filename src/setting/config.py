import copy
import os
import json


# ==================== 配置文件路径设置 ====================
# 获取当前脚本所在目录的绝对路径
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 公共目录路径，用于存储配置文件和公共资源（在项目根目录下）
PUBLIC_DIR = os.path.join(os.path.dirname(os.path.dirname(BASE_DIR)), "public")

# 确保公共目录存在，如果不存在则创建
os.makedirs(PUBLIC_DIR, exist_ok=True)

# 配置文件路径，存储应用程序的所有配置项
CONFIG_FILE = os.path.join(PUBLIC_DIR, "config.json")


def get_project_gridgen_path():
    """固定为项目根目录下的 WW3-Grid-Generator/（网格工具根目录），不从设置或 GRIDGEN_PATH 覆盖。"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    src_dir = os.path.dirname(script_dir)
    project_root = os.path.dirname(src_dir)
    return os.path.normpath(os.path.join(project_root, "WW3-Grid-Generator"))


# 非结构网格：设置页与 Step2 使用的「扁平」键（与 grid.json 互转）；持久化仅使用 unstructured_generator/grid.json
UNST_MSH_GEN_CONFIG_DEFAULTS = {
    "spacing": {
        "hmax": 100.0,
        "hshr": 20.0,
        "hmin": 20.0,
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
        os.path.join(get_project_gridgen_path(), "unstructured_generator", "grid.json")
    )


def get_unst_msh_gen_config_path():
    """兼容旧名：非结构网格统一使用 unstructured_generator/grid.json。"""
    return get_unstructured_grid_json_path()


def default_unst_dem_file_relpath():
    """reference_data 中 RTopo DEM 的相对路径，相对于 unstructured_generator/（与 grid.json 同目录）。"""
    g = get_project_gridgen_path()
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
    """WW3-Grid-Generator/smc_generator/grid.json 绝对路径。"""
    return os.path.normpath(
        os.path.join(get_project_gridgen_path(), "smc_generator", "grid.json")
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
DEFAULT_CONFIG = {
    # ---------- 路径配置 ----------
    # MATLAB 可执行文件的完整路径
    "MATLAB_PATH": "/Applications/MATLAB_R2024a.app/bin/matlab",

    # 已废弃：保留键以兼容旧 config.json；实际目录见 get_project_gridgen_path()
    "GRIDGEN_PATH": "",

    # 参考数据路径（用于网格生成时的参考数据，为空则使用项目 WW3-Grid-Generator/reference_data）
    "REFERENCE_DATA_PATH": "",

    # GridGen 版本类型（"MATLAB" 或 "Python"）
    "GRIDGEN_VERSION": "Python",
    
    # ---------- 网格生成参数配置 ----------
    # 网格 X 方向分辨率（度）
    "DX": "0.05",

    # 网格 Y 方向分辨率（度）
    "DY": "0.05",

    # 嵌套网格外层 X 方向分辨率（度）
    "NESTED_OUTER_DX": "0.05",

    # 嵌套网格外层 Y 方向分辨率（度）
    "NESTED_OUTER_DY": "0.05",

    # 网格南边界纬度（度）
    "LATITUDE_SORTH": "",

    # 网格北边界纬度（度）
    "LATITUDE_NORTH": "",

    # 网格西边界经度（度）
    "LONGITUDE_WEST": "",

    # 网格东边界经度（度）
    "LONGITUDE_EAST": "",

    # 嵌套网格收缩系数（用于嵌套网格的精细区域收缩）
    "NESTED_CONTRACTION_COEFFICIENT": "1.1",
    
    # 水深数据（"GEBCO"、"ETOP1"、"ETOP2"）
    "BATHYMETRY": "GEBCO",
    
    # 海岸边界精度（"最高"、"高"、"中"、"低"）
    "COASTLINE_PRECISION": "最高",
    
    # ---------- Jason-3 数据配置 ----------
    # 本地 Jason-3 数据存储路径
    "JASON_PATH": "",

    # 已移除 Jason-3 自动下载相关配置
    
    # ---------- 工作目录配置 ----------
    # 默认工作目录路径（用于存储 WW3 运行结果）
    "DEFAULT_WORKDIR": os.path.join(os.path.dirname(os.getcwd()), "workSpace"),

    # 默认打开的强迫场文件目录（为空则尝试 public/forcing，再回退到当前工作目录）
    "FORCING_FIELD_DIR_PATH": "",
    
    # ---------- 服务器计算资源配置 ----------
    # 可用的 CPU 组列表（用于作业提交时的 CPU 选择）
    "CPU_GROUP": ["CPU6240R", "CPU6336Y"],

    # 默认使用的 CPU 类型
    "DEFAULT_CPU": "CPU6240R",

    # 计算节点内核数量
    "KERNEL_NUM": "48",

    # 计算节点数量
    "NODE_NUM": "1",
    
    # ---------- 绘图参数配置 ----------
    # 时间步长（小时）
    "PLOT_TIME_STEP": "6",
    
    # 风场时间步长（小时）
    "WIND_FIELD_TIME_STEP": "24",
    
    # 二维谱能量密度最小值（m²/hz/deg）
    "PLOT_ENERGY_THRESHOLD": "0.01",
    
    # 二维谱绘图模式（"归一化" 或 "实际值"）
    "PLOT_SPECTRUM_MODE": "归一化",

    # 计算精度（秒，用于 WW3 计算的时间步长）
    "COMPUTE_PRECISION": "1800",

    # 输出精度（秒，用于 WW3 结果输出的时间间隔）
    "OUTPUT_PRECISION": "3600",
    
    # 文件分割方式（"小时"、"天"、"月"、"年"）
    "FILE_SPLIT": "年",
    
    # ---------- WW3 物理参数配置 ----------
    # 源项选项列表（ST2, ST4, ST6, ST6a, ST6b 等）
    "ST_OPTIONS": [],

    # 频率增量（用于频谱离散化）
    "FREQ_INC": "1.1",

    # 起始频率（Hz）
    "FREQ_START": "0.04118",

    # 频率数量（频谱方向的数量）
    "FREQ_NUM": "32",

    # 方向数量（方向谱的离散方向数）
    "DIR_NUM": "24",

    # 最大时间步长（秒）
    "DTMAX": "900",
    
    # 近岸配置参数
    "GRID_ZLIM": "-0.1",  # 海岸线限制深度 (米)
    "GRID_DMIN": "2.5",   # 绝对最小水深 (米)

    # 空间时间步长（秒）
    "DTXY": "320",

    # 谱空间时间步长（秒）
    "DTKTH": "300",

    # 最小时间步长（秒）
    "DTMIN": "15",
    
    # ---------- WW3 工具路径配置 ----------
    # WW3 二进制文件目录路径（包含 ww3_grid, ww3_prnc, ww3_shel 等可执行文件）
    "WW3BIN_PATH": "",
    
    # ---------- 语言设置 ----------
    # 界面语言（"zh_CN" 或 "en_US"）
    "LANGUAGE": "zh_CN",
    
    # ---------- 界面配置 ----------
    # 主题设置（"AUTO"、"LIGHT"、"DARK"）
    "THEME": "AUTO",
    
    # 运行方式设置（"local"、"server"、"both"）
    "RUN_MODE": "both",
    
    # ---------- 服务器连接配置 ----------
    # 服务器主机地址（SSH 连接地址）
    "SERVER_HOST": "",

    # 服务器 SSH 端口号（默认 22）
    "SERVER_PORT": "22",

    # 服务器 SSH 用户名
    "SERVER_USER": "",

    # 服务器 SSH 密码
    "SERVER_PASSWORD": "",

    # 服务器工作目录路径（用于存储和运行 WW3 作业）
    "SERVER_PATH": "/public/home//workSpace/",
    

    # ---------- 绘图参数配置 ----------
    # 时间步长（小时）
    "PLOT_TIME_STEP": "6",
    
    # 风场时间步长（小时）
    "WIND_FIELD_TIME_STEP": "24",
    
    # 二维谱能量密度最小值（m²/hz/deg）
    "PLOT_ENERGY_THRESHOLD": "0.01",
    
    # 二维谱绘图模式（"归一化" 或 "实际值"）
    "PLOT_SPECTRUM_MODE": "归一化",
    
    # ---------- 界面显示配置 ----------
    # 是否在地图上显示陆地和海岸线（True: 显示, False: 不显示）
    "SHOW_LAND_COASTLINE": True,
    # 最近打开的工作目录列表（最多保存3个，用于快速访问历史工作目录）
    "RECENT_WORKDIRS": []
}


def load_config():
    """加载配置文件，如果不存在则使用默认值"""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
            # 合并默认配置，确保所有键都存在
            merged_config = DEFAULT_CONFIG.copy()
            merged_config.update(config)
            return merged_config
        except Exception as e:
            print(f"加载配置文件失败: {e}，使用默认配置")
            return DEFAULT_CONFIG.copy()
    else:
        # 如果配置文件不存在，创建默认配置文件
        save_config(DEFAULT_CONFIG.copy())
        return DEFAULT_CONFIG.copy()

def save_config(config):
    """保存配置到文件"""
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"保存配置文件失败: {e}")
        return False


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
        default_dir = os.path.join(os.path.dirname(os.path.dirname(BASE_DIR)), "public", "forcing")
        if os.path.exists(default_dir):
            return default_dir
    except Exception:
        pass
    return os.getcwd()

# 加载配置
_config = load_config()

# 全局变量，用于存储配置值（可以在运行时更新）
MATLAB_PATH = None
GRIDGEN_PATH = None
GRIDGEN_BIN_PATH = None
DX = None
DY = None
LATITUDE_SORTH = None
LATITUDE_NORTH = None
LONGITUDE_WEST = None
LONGITUDE_EAST = None
JASON_PATH = None
JASON_REMOTE_PATH = None
JASON_HARMONY_URL = None
CPU_GROUP = None
DEFAULT_CPU = None
KERNEL_NUM = None
NODE_NUM = None
COMPUTE_PRECISION = None
OUTPUT_PRECISION = None
ST_OPTIONS = None
WW3BIN_PATH = None
SERVER_HOST = None
SERVER_PORT = None
SERVER_USER = None
SERVER_PASSWORD = None
SERVER_PATH = None
WIND_FIELD_TIME_STEP = None

def reload_config():
    """重新加载配置并更新全局变量"""
    global _config, MATLAB_PATH, GRIDGEN_PATH, GRIDGEN_BIN_PATH
    global DX, DY, LATITUDE_SORTH, LATITUDE_NORTH, LONGITUDE_WEST, LONGITUDE_EAST
    global JASON_PATH, JASON_REMOTE_PATH, JASON_HARMONY_URL
    global CPU_GROUP, DEFAULT_CPU, KERNEL_NUM, NODE_NUM
    global COMPUTE_PRECISION, OUTPUT_PRECISION, ST_OPTIONS, WW3BIN_PATH
    global SERVER_HOST, SERVER_PORT, SERVER_USER, SERVER_PASSWORD, SERVER_PATH
    global WIND_FIELD_TIME_STEP
    
    _config = load_config()
    
    # 更新全局变量
    matlab_path = _config.get("MATLAB_PATH", DEFAULT_CONFIG["MATLAB_PATH"]).strip()
    if matlab_path:
        MATLAB_PATH = os.path.normpath(matlab_path)  # 规范化路径
    else:
        MATLAB_PATH = matlab_path
    
    GRIDGEN_PATH = get_project_gridgen_path()
    GRIDGEN_BIN_PATH = os.path.normpath(
        os.path.join(GRIDGEN_PATH, "structured_generator", "gridgen")
    )
    
    DX = _config.get("DX", DEFAULT_CONFIG["DX"])
    DY = _config.get("DY", DEFAULT_CONFIG["DY"])
    LATITUDE_SORTH = _config.get("LATITUDE_SORTH", DEFAULT_CONFIG["LATITUDE_SORTH"])
    LATITUDE_NORTH = _config.get("LATITUDE_NORTH", DEFAULT_CONFIG["LATITUDE_NORTH"])
    LONGITUDE_WEST = _config.get("LONGITUDE_WEST", DEFAULT_CONFIG["LONGITUDE_WEST"])
    LONGITUDE_EAST = _config.get("LONGITUDE_EAST", DEFAULT_CONFIG["LONGITUDE_EAST"])
    
    # 第九步常量
    jason_path = _config.get("JASON_PATH", DEFAULT_CONFIG["JASON_PATH"]).strip()
    if jason_path:
        JASON_PATH = os.path.normpath(jason_path)  # 规范化路径
    else:
        JASON_PATH = jason_path
    
    # Jason-3 服务器目录（用于自动下载 Jason-3 数据）
    JASON_REMOTE_PATH = _config.get("JASON_REMOTE_PATH", DEFAULT_CONFIG.get("JASON_REMOTE_PATH", "")).strip()
    # Jason-3 Harmony OGC-API URL（可选，用于在线获取数据）
    JASON_HARMONY_URL = _config.get("JASON_HARMONY_URL", DEFAULT_CONFIG.get("JASON_HARMONY_URL", "")).strip()
    
    # 第四步和第五步的常量
    CPU_GROUP = _config.get("CPU_GROUP", DEFAULT_CONFIG["CPU_GROUP"])
    DEFAULT_CPU = _config.get("DEFAULT_CPU", DEFAULT_CONFIG["DEFAULT_CPU"])
    KERNEL_NUM = _config.get("KERNEL_NUM", DEFAULT_CONFIG["KERNEL_NUM"])
    NODE_NUM = _config.get("NODE_NUM", DEFAULT_CONFIG["NODE_NUM"])
    COMPUTE_PRECISION = _config.get("COMPUTE_PRECISION", DEFAULT_CONFIG["COMPUTE_PRECISION"])
    OUTPUT_PRECISION = _config.get("OUTPUT_PRECISION", DEFAULT_CONFIG["OUTPUT_PRECISION"])
    ST_OPTIONS = _config.get("ST_OPTIONS", DEFAULT_CONFIG["ST_OPTIONS"])
    ww3bin_path = _config.get("WW3BIN_PATH", DEFAULT_CONFIG["WW3BIN_PATH"]).strip()
    if ww3bin_path:
        WW3BIN_PATH = os.path.normpath(ww3bin_path)  # 规范化路径
    else:
        WW3BIN_PATH = ww3bin_path
    
    # 服务器连接相关常量
    SERVER_HOST = _config.get("SERVER_HOST", DEFAULT_CONFIG["SERVER_HOST"])
    SERVER_PORT = _config.get("SERVER_PORT", DEFAULT_CONFIG["SERVER_PORT"])
    SERVER_USER = _config.get("SERVER_USER", DEFAULT_CONFIG["SERVER_USER"])
    SERVER_PASSWORD = _config.get("SERVER_PASSWORD", DEFAULT_CONFIG["SERVER_PASSWORD"])
    SERVER_PATH = _config.get("SERVER_PATH", DEFAULT_CONFIG["SERVER_PATH"])
    
    # 绘图参数
    WIND_FIELD_TIME_STEP = _config.get("WIND_FIELD_TIME_STEP", DEFAULT_CONFIG["WIND_FIELD_TIME_STEP"])

# 初始化全局变量
reload_config()


def add_recent_workdir(workdir):
    """添加最近打开的工作目录到配置（最多保存3个）"""
    if not workdir or not isinstance(workdir, str) or not os.path.exists(workdir):
        return
    
    workdir = os.path.normpath(workdir)
    config = load_config()
    recent_dirs = config.get("RECENT_WORKDIRS", [])
    
    # 如果目录已存在，先移除
    if workdir in recent_dirs:
        recent_dirs.remove(workdir)
    
    # 添加到列表开头
    recent_dirs.insert(0, workdir)
    
    # 只保留最近3个
    recent_dirs = recent_dirs[:3]
    
    # 更新配置
    config["RECENT_WORKDIRS"] = recent_dirs
    save_config(config)


def get_recent_workdirs():
    """获取最近打开的工作目录列表（最多3个）"""
    config = load_config()
    recent_dirs = config.get("RECENT_WORKDIRS", [])
    
    # 过滤掉不存在的目录
    valid_dirs = []
    for dir_path in recent_dirs:
        if os.path.exists(dir_path):
            valid_dirs.append(dir_path)
    
    # 更新配置（移除无效目录）
    if len(valid_dirs) != len(recent_dirs):
        config["RECENT_WORKDIRS"] = valid_dirs
        save_config(config)
    
    return valid_dirs[:3]


def get_default_workdir(create_if_not_exists=True):
    """
    获取默认工作目录路径，自动处理目录不存在的情况
    
    Args:
        create_if_not_exists: 如果目录不存在，是否自动创建（默认 True）
    
    Returns:
        str: 规范化后的工作目录路径，如果获取失败则返回 None
    """
    config = load_config()
    workdir = config.get("DEFAULT_WORKDIR", "")
    
    # 如果配置中的路径为空或无效，使用默认值
    if not workdir or not workdir.strip():
        workdir = DEFAULT_CONFIG.get("DEFAULT_WORKDIR", os.path.join(os.path.dirname(os.getcwd()), "workSpace"))
    
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
