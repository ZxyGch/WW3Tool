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


# ==================== 默认配置值 ====================
DEFAULT_CONFIG = {
    # ---------- 路径配置 ----------
    # MATLAB 可执行文件的完整路径
    "MATLAB_PATH": "/Applications/MATLAB_R2024a.app/bin/matlab",

    # GridGen 工具目录路径（用于生成 WW3 网格）
    "GRIDGEN_PATH": os.path.join(os.path.dirname(os.getcwd()), "gridgen"),

    # 参考数据路径（用于网格生成时的参考数据，为空则使用 GRIDGEN_PATH/reference_data）
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
    "SERVER_PATH": "/public/home/weiyl001/workSpace/",
    

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
    
    gridgen_path = _config.get("GRIDGEN_PATH", "").strip()
    # 如果 gridgen 路径为空，使用默认值 ../gridgen（相对于项目根目录）
    if not gridgen_path:
        # __file__ 是 main/setting/config.py，需要回到项目根目录
        script_dir = os.path.dirname(os.path.abspath(__file__))  # main/setting
        main_dir = os.path.dirname(script_dir)  # main
        project_root = os.path.dirname(main_dir)  # 项目根目录
        gridgen_path = os.path.join(project_root, "gridgen")
    # 规范化路径
    GRIDGEN_PATH = os.path.normpath(gridgen_path) if gridgen_path else gridgen_path
    GRIDGEN_BIN_PATH = os.path.normpath(os.path.join(GRIDGEN_PATH, "matlab")) if GRIDGEN_PATH else None  # 根据 GRIDGEN_PATH 计算
    
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
