"""预处理工作流内置的参数枚举与默认预设。

本模块属于 ``domain/`` 领域层，仅定义常量，不依赖其他层。
选项列表供 ``config_models.ParameterPresets`` 填充默认值，
也被 ``application/configuration.py`` 在 YAML 校验时使用。

主要消费者：
- ``domain/config_models.py``：构造默认预设
- ``application/configuration.py``：校验用户输入是否在允许范围内
- ``desktop/`` 视图层：下拉框与选项列表展示

[EN] Built-in parameter enumerations and default presets for the preprocessing workflow.

This module belongs to the ``domain/`` layer and defines only constants, with no
dependencies on other layers. Option lists are used by
``config_models.ParameterPresets`` to populate defaults, and by
``application/configuration.py`` during YAML validation.

Main consumers:
- ``domain/config_models.py``: construct default presets
- ``application/configuration.py``: validate user input against allowed values
- ``desktop/`` view layer: dropdown and option list display
"""

# 结构化网格可选地形数据源
# [EN] Selectable bathymetry data sources for structured grids
STRUCTURED_BATHYMETRY_OPTIONS = ("GEBCO", "ETOP1", "ETOP2")
# 非结构化 SMC 网格可选地形数据源
# [EN] Selectable bathymetry data sources for unstructured SMC grids
SMC_BATHYMETRY_OPTIONS = ("ETOPO1", "ETOPO2", "GEBCO")
# 海岸线精度档位（与 gridgen 工具参数对应）
# [EN] Coastline precision levels (corresponding to gridgen tool parameters)
COASTLINE_PRECISION_OPTIONS = ("full", "high", "inter", "low", "coarse")
# WW3 输出文件按时间切分的粒度（``single`` = WW3 nodate / TIMESPLIT 0）
# [EN] Time-split granularity for WW3 output files (``single`` = WW3 nodate / TIMESPLIT 0)
FILE_SPLIT_OPTIONS = ("single", "hour", "day", "month", "year")
FILE_SPLIT_LEGACY_ALIASES = {"none": "single"}
# 旧版 UI 误把展示文案写入 yaml（qfluentwidgets addItem 第二参是 icon 不是 userData）
FILE_SPLIT_DISPLAY_ALIASES = {
    "单文件": "single",
    "小时": "hour",
    "天": "day",
    "月": "month",
    "年": "year",
    "single file": "single",
}
FILE_SPLIT_TIMESPLIT = {
    "single": 0,
    "year": 4,
    "month": 6,
    "day": 8,
    "hour": 10,
}


def canonical_file_split(value: object, *, default: str = "year") -> str:
    """Normalize ``ww3.file_split``; accept legacy ``none`` as ``single``."""
    if value is None:
        return default
    raw = str(value).strip().lower()
    if raw in FILE_SPLIT_LEGACY_ALIASES:
        return FILE_SPLIT_LEGACY_ALIASES[raw]
    if raw in FILE_SPLIT_DISPLAY_ALIASES:
        return FILE_SPLIT_DISPLAY_ALIASES[raw]
    if raw in FILE_SPLIT_OPTIONS:
        return raw
    if raw in {"", "null"}:
        return default
    return default


def file_split_timesplit_value(file_split: str) -> int:
    """Map canonical ``ww3.file_split`` to WW3 ``TIMESPLIT`` namelist integer."""
    key = canonical_file_split(file_split)
    return FILE_SPLIT_TIMESPLIT[key]

# WAVEWATCH III 输出场变量代码，与旧版设置页可选字段一致
# [EN] WAVEWATCH III output field variable codes, consistent with legacy settings page selectable fields
OUTPUT_FIELD_OPTIONS = (
    "DPT", "CUR", "WND", "AST", "WLV", "ICE", "IBG", "D50", "IC1", "IC5",
    "HS", "LM", "T02", "T0M1", "T01", "FP", "DIR", "SPR", "DP", "HIG",
    "EF", "TH1M", "STH1M", "TH2M", "STH2M", "WN",
    "PHS", "PTP", "PLP", "PDIR", "PSPR", "PWS", "PDP", "PQP", "PPE",
    "PGW", "PSW", "PTM10", "PT01", "PT02", "PEP", "TWS", "PNR",
    "UST", "CHA", "CGE", "FAW", "TAW", "TWA", "WCC", "WCF", "WCH", "WCM",
    "FWS",
    "SXY", "TWO", "BHD", "FOC", "TUS", "USS", "P2S", "USF", "P2L", "TWI",
    "FIC", "USP", "TOC",
    "ABR", "UBR", "BED", "FBB", "TBB",
    "MSS", "MSC", "MSD", "MCD", "QP", "QKK", "SKW", "EMB",
    "DTD", "FC", "CFX", "CFD", "CFK",
)

# 标准输出方案默认包含的场变量子集
# [EN] Default field variable subset included in the standard output scheme
DEFAULT_OUTPUT_FIELDS = (
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
)

# 命名输出方案：键为方案名，值为场变量代码元组
# [EN] Named output schemes: key is scheme name, value is a tuple of field variable codes
DEFAULT_OUTPUT_SCHEME_PRESETS = {
    "standard": DEFAULT_OUTPUT_FIELDS,
    "with_spectrum": DEFAULT_OUTPUT_FIELDS + ("EF",),
    "all_fields": OUTPUT_FIELD_OPTIONS,
}

# 源项（ST）物理包预设：值为可执行文件所在目录，目录名不限。
# 不内置任何预设，用户通过 params.yml 或设置界面自行配置。
# [EN] Source-term (ST) physics package presets: values are executable directories;
# directory names are unrestricted.
# No built-in presets; users configure via params.yml or the settings UI.
DEFAULT_ST_PRESETS: dict[str, str] = {}
