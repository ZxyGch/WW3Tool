"""预处理工作流内置的参数枚举与默认预设。

本模块属于 ``domain/`` 领域层，仅定义常量，不依赖其他层。
选项列表供 ``config_models.ParameterPresets`` 填充默认值，
也被 ``application/configuration.py`` 在 YAML 校验时使用。

主要消费者：
- ``domain/config_models.py``：构造默认预设
- ``application/configuration.py``：校验用户输入是否在允许范围内
- ``desktop/`` 视图层：下拉框与选项列表展示
"""

# 结构化网格可选地形数据源
STRUCTURED_BATHYMETRY_OPTIONS = ("GEBCO", "ETOP1", "ETOP2")
# 非结构化 SMC 网格可选地形数据源
SMC_BATHYMETRY_OPTIONS = ("ETOPO1", "ETOPO2", "GEBCO")
# 海岸线精度档位（与 gridgen 工具参数对应）
COASTLINE_PRECISION_OPTIONS = ("full", "high", "inter", "low", "coarse")
# WW3 输出文件按时间切分的粒度
FILE_SPLIT_OPTIONS = ("none", "hour", "day", "month", "year")

# WAVEWATCH III 输出场变量代码，与旧版设置页可选字段一致
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
DEFAULT_OUTPUT_SCHEME_PRESETS = {
    "standard": DEFAULT_OUTPUT_FIELDS,
    "with_spectrum": DEFAULT_OUTPUT_FIELDS + ("EF",),
    "all_fields": OUTPUT_FIELD_OPTIONS,
}

# 源项（ST）物理包预设：值为可执行文件目录。
# 旧版 Step4 桥接层会将其转换为 model 根目录后再拼接 ``/exe``。
# 不内置任何预设，用户通过 params.yml 或设置界面自行配置。
DEFAULT_ST_PRESETS: dict[str, str] = {}
