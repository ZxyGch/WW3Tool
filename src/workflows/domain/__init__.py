"""WW3Tool 无界面工作流的领域模型公共导出。

本包属于 ``domain/`` 层，仅包含数据类、枚举与常量，不依赖 application、
infrastructure 或 UI。此处集中 re-export 供上层 ``from workflows.domain import ...`` 使用。

主要消费者：
- ``application/configuration.py``：YAML 解析与校验
- ``application/*`` 各用例模块
- ``desktop/view_models/``：桌面端视图模型

[EN] Public exports of domain models for WW3Tool headless workflows.

This package belongs to the ``domain/`` layer and contains only data classes,
enums, and constants. It does not depend on application, infrastructure, or UI.
Symbols are re-exported here for convenient ``from workflows.domain import ...``
usage by upper layers.

Main consumers:
- ``application/configuration.py``: YAML parsing and validation
- ``application/*`` use-case modules
- ``desktop/view_models/``: desktop view models
"""

from .config_models import (
    CalcConfig,
    ForcingConfig,
    GridConfig,
    GridRegion,
    ParameterPresets,
    PipelineConfig,
    PointConfig,
    SMCGridSettings,
    SlurmConfig,
    StructuredGridSettings,
    TrackPointConfig,
    UnstructuredGridSettings,
    WW3Config,
    WorkdirConfig,
)
from .forcing_fields import FORCING_FIELD_ORDER, ForcingField, Step2Files, Step2State
from .parameter_catalog import (
    COASTLINE_PRECISION_OPTIONS,
    DEFAULT_OUTPUT_FIELDS,
    FILE_SPLIT_OPTIONS,
    OUTPUT_FIELD_OPTIONS,
    SMC_BATHYMETRY_OPTIONS,
    DEFAULT_ST_PRESETS,
    STRUCTURED_BATHYMETRY_OPTIONS,
)

__all__ = [
    "CalcConfig",
    "ForcingConfig",
    "GridConfig",
    "GridRegion",
    "ParameterPresets",
    "PipelineConfig",
    "PointConfig",
    "SMCGridSettings",
    "SlurmConfig",
    "StructuredGridSettings",
    "TrackPointConfig",
    "UnstructuredGridSettings",
    "WW3Config",
    "WorkdirConfig",
    "FORCING_FIELD_ORDER",
    "ForcingField",
    "Step2Files",
    "Step2State",
    "COASTLINE_PRECISION_OPTIONS",
    "DEFAULT_OUTPUT_FIELDS",
    "FILE_SPLIT_OPTIONS",
    "OUTPUT_FIELD_OPTIONS",
    "SMC_BATHYMETRY_OPTIONS",
    "DEFAULT_ST_PRESETS",
    "STRUCTURED_BATHYMETRY_OPTIONS",
]
