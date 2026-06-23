"""无界面预处理 YAML 接口对应的流水线配置数据类。

本模块属于 ``domain/`` 领域层，将 ``params.yml`` 各段落映射为类型化的
``dataclass``，不含解析、校验或 I/O 逻辑。

主要消费者：
- ``application/configuration.py``：YAML 加载、默认值合并与校验
- ``application/*`` 各用例：只读访问已解析的 ``PipelineConfig``
- ``desktop/view_models/``：桌面端与 CLI 共用同一套配置模型

[EN] Pipeline configuration data classes for the headless preprocessing YAML interface.

This module belongs to the ``domain/`` layer and maps sections of ``params.yml``
to typed ``dataclass`` instances. It contains no parsing, validation, or I/O logic.

Main consumers:
- ``application/configuration.py``: YAML loading, default merging, and validation
- ``application/*`` use cases: read-only access to the resolved ``PipelineConfig``
- ``desktop/view_models/``: desktop and CLI share the same configuration models
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

    [EN] Local working directory path.

    Key fields:
    - ``path``: WW3 case root directory; forcing, grid, and namelist files are all generated under it
    """

    path: Path


@dataclass
class ForcingConfig:
    """强迫场源文件与处理选项（对应 YAML ``forcing:`` 段）。

    关键字段：
    - ``wind`` / ``current`` / ``level`` / ``ice``：各场 NetCDF 源文件路径
    - ``process_mode``：``copy`` 或 ``move``，控制写入工作目录的方式
    - ``auto_associate``：是否根据文件名自动匹配场类型

    [EN] Forcing source files and processing options (corresponds to YAML ``forcing:`` section).

    Key fields:
    - ``wind`` / ``current`` / ``level`` / ``ice``: NetCDF source file paths for each field
    - ``process_mode``: ``copy`` or ``move``, controls how files are written to the working directory
    - ``auto_associate``: whether to automatically match field types based on filenames
    """

    wind: Optional[Path] = None
    current: Optional[Path] = None
    level: Optional[Path] = None
    ice: Optional[Path] = None
    process_mode: Optional[str] = None
    auto_associate: Optional[bool] = None


@dataclass
class GridRegion:
    """矩形网格区域的经纬度范围与分辨率。

    关键字段：
    - ``dx`` / ``dy``：经向、纬向格距（度）
    - ``lon`` / ``lat``：``[min, max]`` 形式的经度、纬度边界

    [EN] Longitude/latitude extent and resolution of a rectangular grid region.

    Key fields:
    - ``dx`` / ``dy``: zonal and meridional grid spacing (degrees)
    - ``lon`` / ``lat``: longitude and latitude bounds as ``[min, max]``
    - ``compute_precision`` / ``output_precision``: 该层独立的 ww3_shel 积分步 /
      输出步（秒）；省略时回退全局 ``ww3.compute_precision`` / ``output_precision``。
    """

    dx: Optional[float] = None
    dy: Optional[float] = None
    lon: Optional[List[float]] = None
    lat: Optional[List[float]] = None
    compute_precision: Optional[str] = None
    output_precision: Optional[str] = None


@dataclass
class StructuredGridSettings:
    """结构化（rectilinear）网格生成参数。

    关键字段：
    - ``bathymetry``：地形数据源名称（见 ``STRUCTURED_BATHYMETRY_OPTIONS``）
    - ``coastline_precision``：海岸线精度档位
    - ``min_dist`` / ``cut_off`` / ``lim_bathy`` 等：gridgen 数值阈值

    [EN] Structured (rectilinear) grid generation parameters.

    Key fields:
    - ``bathymetry``: bathymetry data source name (see ``STRUCTURED_BATHYMETRY_OPTIONS``)
    - ``coastline_precision``: coastline precision level
    - ``min_dist`` / ``cut_off`` / ``lim_bathy`` etc.: gridgen numerical thresholds
    """

    bathymetry: Optional[str] = None
    coastline_precision: Optional[str] = None
    min_dist: Optional[float] = None
    cut_off: Optional[float] = None
    lim_bathy: Optional[float] = None
    lim_val: Optional[float] = None
    split_lim: Optional[float] = None
    lake_tol: Optional[float] = None


@dataclass
class SMCGridSettings:
    """球面多重单元（SMC）非结构化网格参数。

    关键字段：
    - ``bathymetry`` / ``bathy_convention``：地形源与高程约定
    - ``n_levels`` / ``wlevel``：多级网格与水位参考
    - ``options``：透传给 gridgen 的额外键值对

    [EN] Spherical Multi-Cell (SMC) unstructured grid parameters.

    Key fields:
    - ``bathymetry`` / ``bathy_convention``: bathymetry source and elevation convention
    - ``n_levels`` / ``wlevel``: multi-level grid and water level reference
    - ``options``: extra key-value pairs passed through to gridgen
    """

    bathymetry: Optional[str] = None
    bathy_convention: Optional[str] = None
    n_levels: Optional[int] = None
    wlevel: Optional[float] = None
    depmin: Optional[float] = None
    dshalw: Optional[float] = None
    generate_boundary_cells: Optional[bool] = None
    msea: Optional[int] = None
    options: Dict[str, Any] = field(default_factory=dict)


@dataclass
class UnstructuredGridSettings:
    """三角非结构化网格（triangle mesh）参数。

    关键字段：
    - ``hmax`` / ``hmin`` / ``hshr`` / ``nwav``：网格尺寸与波数相关控制量
    - ``deep_ocean_threshold_m`` / ``margin_deg``：深海阈值与外扩边距
    - ``options``：底层 gridgen 额外选项

    [EN] Triangular unstructured grid (triangle mesh) parameters.

    Key fields:
    - ``hmax`` / ``hmin`` / ``hshr`` / ``nwav``: mesh size and wavenumber-related control quantities
    - ``deep_ocean_threshold_m`` / ``margin_deg``: deep-ocean threshold and outward margin
    - ``options``: underlying gridgen extra options
    """

    hmax: Optional[float] = None
    hmin: Optional[float] = None
    hshr: Optional[float] = None
    nwav: Optional[int] = None
    dhdx: Optional[float] = None
    deep_ocean_threshold_m: Optional[float] = None
    margin_deg: Optional[float] = None
    edge_segments: Optional[int] = None
    options: Dict[str, Any] = field(default_factory=dict)


@dataclass
class GridConfig:
    """网格类型、嵌套区域与分类型子配置的聚合（对应 YAML ``grid:`` 段）。

    关键字段：
    - ``mesh_type``：``structured`` / ``smc`` / ``unstructured``
    - ``outer`` / ``inner``：外圈与可选内圈（嵌套）区域
    - ``structured`` / ``smc`` / ``unstructured``：按 ``mesh_type`` 选用的子配置

    [EN] Aggregation of grid type, nested regions, and type-specific sub-configs
    (corresponds to YAML ``grid:`` section).

    Key fields:
    - ``mesh_type``: ``structured`` / ``smc`` / ``unstructured``
    - ``outer`` / ``inner``: outer and optional inner (nested) regions
    - ``structured`` / ``smc`` / ``unstructured``: sub-config selected by ``mesh_type``
    """

    mesh_type: Optional[str] = None
    grid_type: Optional[str] = None
    lon: Optional[List[float]] = None
    lat: Optional[List[float]] = None
    outer: Optional[GridRegion] = None
    inner: Optional[GridRegion] = None
    # 嵌套各层（粗 → 细，level0 最粗）；normal 时只有 1 层。outer=levels[0]、inner=levels[-1]。
    nested_levels: Optional[List[GridRegion]] = None
    gridgen_version: Optional[str] = None
    reference_data_path: Optional[Path] = None
    nested_contraction_coefficient: Optional[float] = None
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

    [EN] Single-point spectral output location (used when ``calc.mode=point``).

    Key fields:
    - ``lon`` / ``lat``: point coordinates (degrees)
    - ``name``: station name written to the namelist
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

    [EN] A space-time point along a track output path (used when ``calc.mode=track``).

    Key fields:
    - ``datetime``: ISO or namelist-parseable time string
    - ``lon`` / ``lat``: position at that time
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

    [EN] Computation mode and point/track configuration (corresponds to YAML ``calc:`` section).

    Key fields:
    - ``mode``: ``region`` / ``point`` / ``track``, etc.
    - ``points`` / ``track_points``: mode-specific spatial sampling lists
    """

    mode: Optional[str] = None
    points: List[PointConfig] = field(default_factory=list)
    track_points: List[TrackPointConfig] = field(default_factory=list)


@dataclass
class ParameterPresets:
    """UI 与校验用的参数枚举预设副本（来自 ``parameter_catalog``）。

    在 ``PipelineConfig`` 中携带一份可变副本，便于运行时覆盖默认值
    而不修改模块级常量。

    [EN] Parameter enumeration preset copies for UI and validation (from ``parameter_catalog``).

    Carries a mutable copy inside ``PipelineConfig`` so that defaults can be
    overridden at runtime without modifying module-level constants.
    """

    output_scheme: Dict[str, List[str]] = field(
        default_factory=lambda: {
            name: list(fields) for name, fields in DEFAULT_OUTPUT_SCHEME_PRESETS.items()
        }
    )
    server_st: Dict[str, str] = field(default_factory=lambda: dict(DEFAULT_ST_PRESETS))
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
    - ``output_scheme`` / ``st``：输出场方案与源项物理包（``st`` 已迁移至 ``slurm.server_st``，保留向后兼容）

    [EN] WAVEWATCH III run period and output scheme (corresponds to YAML ``ww3:`` section).

    Key fields:
    - ``start_date`` / ``end_date``: simulation start and end times
    - ``compute_precision`` / ``output_precision``: integration and output time steps (seconds)
    - ``inner_*``: independent time steps for the nested inner grid (optional)
    - ``output_scheme``: output field scheme
    - ``st``: DEPRECATED — use ``slurm.server_st`` instead; kept for backward compatibility
    """

    start_date: str = ""
    end_date: str = ""
    compute_precision: Optional[str] = None
    output_precision: Optional[str] = None
    inner_compute_precision: Optional[str] = None
    inner_output_precision: Optional[str] = None
    file_split: Optional[str] = None
    output_scheme: Optional[str] = None
    st: Optional[str] = None


@dataclass
class WW3GridSettings:
    """``ww3_grid.nml`` 中谱与网格相关数值参数。

    ``parameters`` 键为 namelist 变量名（含 ``%`` 分隔符），值为字符串形式，
    由 namelist 写入层原样输出。

    [EN] Spectral and grid-related numerical parameters in ``ww3_grid.nml``.

    ``parameters`` keys are namelist variable names (including the ``%`` separator),
    and values are strings that are written as-is by the namelist writer layer.
    """

    parameters: Optional[Dict[str, str]] = None


@dataclass
class SlurmConfig:
    """远程 SLURM 作业资源（对应 YAML ``slurm:`` 段）。

    关键字段：
    - ``job_name``：Slurm 作业名，写入 ``server.sh`` 的 ``#SBATCH -J``
    - ``cpu`` / ``nodes`` / ``cores``：分区与并行规模
    - ``server_st``：服务器上选择的 ST 版本名称（对应 presets.server_st 的键）

    [EN] Remote SLURM job resources (corresponds to YAML ``slurm:`` section).

    Key fields:
    - ``job_name``: Slurm job name, written to ``#SBATCH -J`` in ``server.sh``
    - ``cpu`` / ``nodes`` / ``cores``: partition and parallelism scale
    - ``server_st``: selected ST version name (key from presets.server_st)
    """

    job_name: Optional[str] = None
    cpu: Optional[str] = None
    nodes: Optional[str] = None
    cores: Optional[str] = None
    server_st: Optional[str] = None


@dataclass
class ServerConfig:
    """SSH 远程服务器连接与远端工作目录（对应 YAML ``server:`` 段）。

    关键字段：
    - ``host`` / ``port`` / ``user``：连接目标
    - ``password`` / ``key_file``：认证方式（二选一或组合）
    - ``ssh_config_host``：``~/.ssh/config`` 中的 Host 别名（设置后连接时现场解析，不导入到其它字段）
    - ``default_remote_dir``：默认远程基础目录（从设置页写入）
    - ``remote_dir``：实际远程工作目录（第六步输入框写入，为空时回退到 default_remote_dir + 工作目录名）

    [EN] SSH remote server connection and remote working directory (corresponds to YAML ``server:`` section).

    Key fields:
    - ``host`` / ``port`` / ``user``: connection target
    - ``password`` / ``key_file``: authentication method (either or combined)
    - ``ssh_config_host``: Host alias in ``~/.ssh/config`` (resolved at connect time, not copied to other fields)
    - ``default_remote_dir``: default remote base directory (set from the settings page)
    - ``remote_dir``: actual remote working directory (set from step-6 input; falls back to default_remote_dir + workdir name when empty)
    """

    host: str = ""
    port: Optional[int] = None
    user: str = ""
    password: str = ""
    key_file: Optional[Path] = None
    ssh_config_host: str = ""
    default_remote_dir: str = ""
    remote_dir: str = ""


@dataclass
class WaveMapsConfig:
    """波高填色/等值线地图后处理选项。

    [EN] Wave height filled-color / contour map post-processing options.
    """

    time_step_hours: Optional[float] = None
    figsize: Optional[List[float]] = None
    dpi: Optional[int] = None
    generate_video: bool = False
    show_land_coastline: bool = True
    output_folder: Optional[Path] = None


@dataclass
class SpectrumConfig:
    """二维方向谱绘图选项。

    [EN] 2-D directional spectrum plotting options.
    """

    time_step_hours: Optional[float] = None
    energy_threshold: Optional[float] = None
    plot_mode: Optional[str] = None


@dataclass
class Jason3Config:
    """WW3 结果与 Jason-3 卫星高度计匹配选项。

    [EN] Options for matching WW3 results with Jason-3 satellite altimeter data.
    """

    data_folder: Optional[Path] = None
    lon_lat: List[float] = field(default_factory=list)
    time_range: List[str] = field(default_factory=list)
    max_dist_deg: Optional[float] = None
    time_window_hours: Optional[float] = None


@dataclass
class NDBCConfig:
    """WW3 结果与 NDBC 浮标观测匹配或下载选项。

    [EN] Options for matching WW3 results with NDBC buoy observations or downloading data.
    """

    data_folder: Optional[Path] = None
    download: bool = False
    time_range: List[str] = field(default_factory=list)


@dataclass
class WindFieldConfig:
    """风场填色图后处理选项。

    [EN] Wind field filled-color map post-processing options.
    """

    time_step_hours: Optional[float] = None
    flag_type: Optional[str] = None
    flag_density: Optional[int] = None


@dataclass
class PlotConfig:
    """后处理绘图与验证任务的聚合配置（对应 YAML ``plot:`` 段）。

    关键字段：
    - ``wave_maps`` / ``spectrum`` / ``jason3`` / ``ndbc``：各子任务开关与参数

    [EN] Aggregated configuration for post-processing plotting and validation tasks
    (corresponds to YAML ``plot:`` section).

    Key fields:
    - ``wave_maps`` / ``spectrum`` / ``jason3`` / ``ndbc``: switches and parameters for each sub-task
    """

    wave_maps: WaveMapsConfig = field(default_factory=WaveMapsConfig)
    spectrum: SpectrumConfig = field(default_factory=SpectrumConfig)
    jason3: Jason3Config = field(default_factory=Jason3Config)
    ndbc: NDBCConfig = field(default_factory=NDBCConfig)
    wind_field: WindFieldConfig = field(default_factory=WindFieldConfig)


@dataclass
class PathsConfig:
    """外部工具与数据目录路径（对应 YAML ``paths:`` 段）。

    这些路径原存储在 ``config.json``，现迁移至 ``params.yml`` 以便按工作区管理。
    所有字段均为可选，省略时回退到项目默认路径。

    [EN] External tool and data directory paths (corresponds to YAML ``paths:`` section).

    These paths were previously stored in ``config.json`` and have been migrated
    to ``params.yml`` for per-workspace management. All fields are optional;
    omitted fields fall back to project default paths.
    """

    matlab_path: str = ""
    ww3bin_path: str = ""
    jason_path: str = ""
    ndbc_path: str = ""
    jason3_download_url: str = ""


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

    [EN] Root configuration object for the full preprocessing/post-processing pipeline.

    Assembled by ``load_pipeline_config`` from YAML and default values at each layer,
    spanning the entire forcing -> grid -> ww3 namelist -> plot / remote workflow.

    Key fields:
    - ``source_path``: original ``params.yml`` path (optional, for traceability)
    - ``base_dir``: base directory for resolving relative paths
    - ``workdir``: local case working directory
    - remaining fields: nested dataclasses for each business section
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
    paths: PathsConfig = field(default_factory=PathsConfig)
