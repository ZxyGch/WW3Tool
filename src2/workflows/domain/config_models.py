"""无界面预处理 YAML 接口对应的流水线配置数据类。

本模块属于 ``domain/`` 领域层，将 ``params.yml`` 各段落映射为类型化的
``dataclass``，不含解析、校验或 I/O 逻辑。

主要消费者：
- ``application/configuration.py``：YAML 加载、默认值合并与校验
- ``application/*`` 各用例：只读访问已解析的 ``PipelineConfig``
- ``desktop/view_models/``：桌面端与 CLI 共用同一套配置模型
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from .parameter_catalog import (
    COASTLINE_PRECISION_OPTIONS,
    DEFAULT_OUTPUT_SCHEME_PRESETS,
    DEFAULT_ST_PRESETS,
    FILE_SPLIT_OPTIONS,
    SMC_BATHYMETRY_OPTIONS,
    STRUCTURED_BATHYMETRY_OPTIONS,
)


NumberPair = Sequence[float]


@dataclass
class WorkdirConfig:
    """本地工作目录路径。

    关键字段：
    - ``path``：WW3 案例根目录，强迫场、网格与 namelist 均在其下生成
    """

    path: Path


@dataclass
class ForcingConfig:
    """强迫场源文件与处理选项（对应 YAML ``forcing:`` 段）。

    关键字段：
    - ``wind`` / ``current`` / ``level`` / ``ice``：各场 NetCDF 源文件路径
    - ``process_mode``：``copy`` 或 ``move``，控制写入工作目录的方式
    - ``converted``：是否已由 Step 1 写回转换后的工作目录文件路径
    - ``auto_associate``：是否根据文件名自动匹配场类型
    """

    wind: Optional[Path] = None
    current: Optional[Path] = None
    level: Optional[Path] = None
    ice: Optional[Path] = None
    process_mode: str = "copy"
    auto_associate: bool = True
    converted: bool = False


@dataclass
class GridRegion:
    """矩形网格区域的经纬度范围与分辨率。

    关键字段：
    - ``dx`` / ``dy``：经向、纬向格距（度）
    - ``lon`` / ``lat``：``[min, max]`` 形式的经度、纬度边界
    """

    dx: float = 0.05
    dy: float = 0.05
    lon: List[float] = field(default_factory=lambda: [110.0, 130.0])
    lat: List[float] = field(default_factory=lambda: [10.0, 30.0])


@dataclass
class StructuredGridSettings:
    """结构化（rectilinear）网格生成参数。

    关键字段：
    - ``bathymetry``：地形数据源名称（见 ``STRUCTURED_BATHYMETRY_OPTIONS``）
    - ``coastline_precision``：海岸线精度档位
    - ``min_dist`` / ``cut_off`` / ``lim_bathy`` 等：gridgen 数值阈值
    """

    bathymetry: str = "GEBCO"
    coastline_precision: str = "full"
    min_dist: float = 20.0
    cut_off: float = 0.0
    lim_bathy: float = 0.4
    lim_val: float = 0.5
    split_lim: float = 0.0
    lake_tol: float = 50.0


@dataclass
class SMCGridSettings:
    """球面多重单元（SMC）非结构化网格参数。

    关键字段：
    - ``bathymetry`` / ``bathy_convention``：地形源与高程约定
    - ``n_levels`` / ``wlevel``：多级网格与水位参考
    - ``options``：透传给 gridgen 的额外键值对
    """

    bathymetry: str = "ETOPO2"
    bathy_convention: str = "elevation"
    n_levels: int = 2
    wlevel: float = 0.0
    depmin: float = 0.0
    dshalw: float = -150.0
    generate_boundary_cells: bool = True
    msea: int = 1
    options: Dict[str, Any] = field(default_factory=dict)


@dataclass
class UnstructuredGridSettings:
    """三角非结构化网格（triangle mesh）参数。

    关键字段：
    - ``hmax`` / ``hshr`` / ``nwav``：网格尺寸与波数相关控制量
    - ``deep_ocean_threshold_m`` / ``margin_deg``：深海阈值与外扩边距
    - ``options``：底层 gridgen 额外选项
    """

    hmax: float = 100.0
    hshr: float = 20.0
    nwav: int = 400
    dhdx: float = 0.05
    deep_ocean_threshold_m: float = 4000.0
    margin_deg: float = 1.0
    edge_segments: int = 64
    options: Dict[str, Any] = field(default_factory=dict)


@dataclass
class GridConfig:
    """网格类型、嵌套区域与分类型子配置的聚合（对应 YAML ``grid:`` 段）。

    关键字段：
    - ``mesh_type``：``structured`` / ``smc`` / ``unstructured``
    - ``outer`` / ``inner``：外圈与可选内圈（嵌套）区域
    - ``structured`` / ``smc`` / ``unstructured``：按 ``mesh_type`` 选用的子配置
    """

    mesh_type: str = "structured"
    grid_type: str = "normal"
    generated: bool = False
    outer: GridRegion = field(default_factory=GridRegion)
    inner: Optional[GridRegion] = None
    gridgen_version: str = "Python"
    reference_data_path: Optional[Path] = None
    nested_contraction_coefficient: float = 1.3
    structured: StructuredGridSettings = field(default_factory=StructuredGridSettings)
    smc: SMCGridSettings = field(default_factory=SMCGridSettings)
    unstructured: UnstructuredGridSettings = field(default_factory=UnstructuredGridSettings)
    options: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PointConfig:
    """单点谱输出位置（``calc.mode=point`` 时使用）。

    关键字段：
    - ``lon`` / ``lat``：点位坐标（度）
    - ``name``：写入 namelist 的站点名称
    """

    lon: float
    lat: float
    name: str = "Point"


@dataclass
class TrackPointConfig:
    """沿轨输出路径上的一个时空点（``calc.mode=track`` 时使用）。

    关键字段：
    - ``datetime``：ISO 或 namelist 可解析的时间字符串
    - ``lon`` / ``lat``：该时刻位置
    """

    datetime: str
    lon: float
    lat: float
    name: str = "Track"


@dataclass
class CalcConfig:
    """计算模式与点位/轨迹配置（对应 YAML ``calc:`` 段）。

    关键字段：
    - ``mode``：``region`` / ``point`` / ``track`` 等
    - ``points`` / ``track_points``：模式相关的空间采样列表
    """

    mode: str = "region"
    points: List[PointConfig] = field(default_factory=list)
    track_points: List[TrackPointConfig] = field(default_factory=list)


@dataclass
class ParameterPresets:
    """UI 与校验用的参数枚举预设副本（来自 ``parameter_catalog``）。

    在 ``PipelineConfig`` 中携带一份可变副本，便于运行时覆盖默认值
    而不修改模块级常量。
    """

    output_scheme: Dict[str, List[str]] = field(
        default_factory=lambda: {
            name: list(fields) for name, fields in DEFAULT_OUTPUT_SCHEME_PRESETS.items()
        }
    )
    st: Dict[str, str] = field(default_factory=lambda: dict(DEFAULT_ST_PRESETS))
    structured_bathymetry: List[str] = field(default_factory=lambda: list(STRUCTURED_BATHYMETRY_OPTIONS))
    smc_bathymetry: List[str] = field(default_factory=lambda: list(SMC_BATHYMETRY_OPTIONS))
    coastline_precision: List[str] = field(default_factory=lambda: list(COASTLINE_PRECISION_OPTIONS))
    file_split: List[str] = field(default_factory=lambda: list(FILE_SPLIT_OPTIONS))


@dataclass
class WW3Config:
    """WAVEWATCH III 运行时间与输出方案（对应 YAML ``ww3:`` 段）。

    关键字段：
    - ``start_date`` / ``end_date``：模拟起止时间
    - ``compute_precision`` / ``output_precision``：积分与输出时间步（秒）
    - ``inner_*``：嵌套内圈网格的独立时间步（可选）
    - ``output_scheme`` / ``st``：输出场方案与源项物理包
    """

    start_date: str = ""
    end_date: str = ""
    compute_precision: str = "1800"
    output_precision: str = "3600"
    inner_compute_precision: Optional[str] = None
    inner_output_precision: Optional[str] = None
    file_split: str = "year"
    output_scheme: str = "standard"
    st: str = "ST2"


@dataclass
class WW3GridSettings:
    """``ww3_grid.nml`` 中谱与网格相关数值参数。

    ``parameters`` 键为 namelist 变量名（含 ``%`` 分隔符），值为字符串形式，
    由 namelist 写入层原样输出。
    """

    parameters: Dict[str, str] = field(
        default_factory=lambda: {
            "SPECTRUM%XFR": "1.1",
            "SPECTRUM%FREQ1": "0.04118",
            "SPECTRUM%NK": "32",
            "SPECTRUM%NTH": "24",
            "TIMESTEPS%DTMAX": "900",
            "TIMESTEPS%DTXY": "320",
            "TIMESTEPS%DTKTH": "300",
            "TIMESTEPS%DTMIN": "15",
            "GRID%ZLIM": "-0.1",
            "GRID%DMIN": "2.5",
        }
    )


@dataclass
class SlurmConfig:
    """远程 SLURM 作业资源与脚本路径（对应 YAML ``slurm:`` 段）。

    关键字段：
    - ``cpu`` / ``nodes`` / ``cores``：分区与并行规模
    - ``server_script_path``：本地 ``server.sh`` 模板路径（上传前可选）
    """

    cpu: str = "CPU6240R"
    nodes: str = "1"
    cores: str = "48"
    server_script_path: Optional[Path] = None


@dataclass
class ServerConfig:
    """SSH 远程服务器连接与远端工作目录（对应 YAML ``server:`` 段）。

    关键字段：
    - ``host`` / ``port`` / ``user``：连接目标
    - ``password`` / ``key_file``：认证方式（二选一或组合）
    - ``remote_dir``：远端案例目录
    """

    host: str = ""
    port: int = 22
    user: str = ""
    password: str = ""
    key_file: Optional[Path] = None
    remote_dir: str = ""


@dataclass
class WaveMapsConfig:
    """波高填色/等值线地图后处理选项。"""

    enabled: bool = True
    time_step_hours: float = 1.0
    figsize: List[float] = field(default_factory=lambda: [16.0, 12.0])
    dpi: int = 300
    generate_video: bool = False
    show_land_coastline: bool = True
    output_folder: Optional[Path] = None


@dataclass
class SpectrumConfig:
    """二维方向谱绘图选项。"""

    enabled: bool = False
    time_step_hours: float = 24.0
    energy_threshold: float = 0.01
    plot_mode: str = "最大值归一化"


@dataclass
class Jason3Config:
    """WW3 结果与 Jason-3 卫星高度计匹配选项。"""

    enabled: bool = False
    data_folder: Optional[Path] = None
    lon_lat: List[float] = field(default_factory=list)
    time_range: List[str] = field(default_factory=list)
    max_dist_deg: float = 0.125
    time_window_hours: float = 0.5


@dataclass
class NDBCConfig:
    """WW3 结果与 NDBC 浮标观测匹配或下载选项。"""

    enabled: bool = False
    data_folder: Optional[Path] = None
    download: bool = False
    time_range: List[str] = field(default_factory=list)


@dataclass
class WindFieldConfig:
    """风场填色图后处理选项。"""

    time_step_hours: float = 24.0
    flag_type: str = "箭头"
    flag_density: int = 10


@dataclass
class PlotConfig:
    """后处理绘图与验证任务的聚合配置（对应 YAML ``plot:`` 段）。

    关键字段：
    - ``result_folder``：WW3 输出 NetCDF 所在目录（默认可由 workdir 推导）
    - ``wave_maps`` / ``spectrum`` / ``jason3`` / ``ndbc``：各子任务开关与参数
    """

    result_folder: Optional[Path] = None
    wave_maps: WaveMapsConfig = field(default_factory=WaveMapsConfig)
    spectrum: SpectrumConfig = field(default_factory=SpectrumConfig)
    jason3: Jason3Config = field(default_factory=Jason3Config)
    ndbc: NDBCConfig = field(default_factory=NDBCConfig)
    wind_field: WindFieldConfig = field(default_factory=WindFieldConfig)


@dataclass
class PipelineConfig:
    """完整预处理/后处理流水线的根配置对象。

    由 ``load_pipeline_config`` 从 YAML 与各层默认值合并而成，贯穿
    forcing → grid → ww3 namelist → plot / remote 全流程。

    关键字段：
    - ``source_path``：原始 ``params.yml`` 路径（可选，用于溯源）
    - ``base_dir``：相对路径解析基准目录
    - ``workdir``：本地案例工作目录
    - 其余字段：各业务段对应的嵌套 dataclass
    """

    source_path: Optional[Path]
    base_dir: Path
    workdir: WorkdirConfig
    presets: ParameterPresets = field(default_factory=ParameterPresets)
    forcing: ForcingConfig = field(default_factory=ForcingConfig)
    grid: GridConfig = field(default_factory=GridConfig)
    calc: CalcConfig = field(default_factory=CalcConfig)
    ww3: WW3Config = field(default_factory=WW3Config)
    ww3_grid: WW3GridSettings = field(default_factory=WW3GridSettings)
    slurm: SlurmConfig = field(default_factory=SlurmConfig)
    plot: PlotConfig = field(default_factory=PlotConfig)
    server: ServerConfig = field(default_factory=ServerConfig)
