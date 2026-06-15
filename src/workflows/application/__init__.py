"""WW3Tool 无界面工作流的应用层用例包。

本包聚合预处理、网格、绘图与远程运维等用例，供 CLI 与桌面端调用。
采用惰性导入（``__getattr__``），避免在仅加载配置或查看帮助时
拉取完整的科学计算依赖栈。

流水线步骤对应关系
------------------
- **Step 1 强迫场**：``run_prepare_forcing``、``report_forcing_file_overviews``
- **Step 2 网格**：``run_generate_grid``、``read_wind_bounds``、``visualize_grid`` 等
- **完整预处理**：``run_pipeline``（强迫场 + 网格 + WW3 namelist）
- **配置**：``load_pipeline_config``、``parse_pipeline_config``、``validate_pipeline_config``

输入/输出
---------
- 输入：``params.yml`` 解析后的 ``PipelineConfig``，或 YAML 文件路径
- 输出：各步骤对应的结果 dataclass（``PipelineResult``、``GridGenerationResult`` 等）
"""

__all__ = [
    "ConfigError",
    "PipelineResult",
    "GridGenerationResult",
    "GridBounds",
    "GridPreviewResult",
    "ForcingMergeResult",
    "load_pipeline_config",
    "parse_pipeline_config",
    "report_forcing_file_overviews",
    "run_generate_grid",
    "run_merge_forcing",
    "read_wind_bounds",
    "render_region_map",
    "scale_nested_region",
    "visualize_grid",
    "run_pipeline",
    "run_prepare_forcing",
    "validate_pipeline_config",
]


def __getattr__(name):
    """按需延迟导入子模块中的公开符号，减轻启动时的依赖负担。"""
    if name in {"ConfigError", "load_pipeline_config", "parse_pipeline_config", "validate_pipeline_config"}:
        from .configuration import ConfigError, load_pipeline_config, parse_pipeline_config, validate_pipeline_config

        return {
            "ConfigError": ConfigError,
            "load_pipeline_config": load_pipeline_config,
            "parse_pipeline_config": parse_pipeline_config,
            "validate_pipeline_config": validate_pipeline_config,
        }[name]
    if name == "report_forcing_file_overviews":
        from .forcing_inspection import report_forcing_file_overviews

        return report_forcing_file_overviews
    if name in {"ForcingMergeResult", "run_merge_forcing"}:
        from .forcing_merge import ForcingMergeResult, run_merge_forcing

        return {
            "ForcingMergeResult": ForcingMergeResult,
            "run_merge_forcing": run_merge_forcing,
        }[name]
    if name in {"GridGenerationResult", "run_generate_grid"}:
        from .grid_preparation import GridGenerationResult, run_generate_grid

        return {
            "GridGenerationResult": GridGenerationResult,
            "run_generate_grid": run_generate_grid,
        }[name]
    if name in {"GridBounds", "GridPreviewResult", "read_wind_bounds", "render_region_map", "scale_nested_region", "visualize_grid"}:
        from .grid_tools import (
            GridBounds,
            GridPreviewResult,
            read_wind_bounds,
            render_region_map,
            scale_nested_region,
            visualize_grid,
        )

        return {
            "GridBounds": GridBounds,
            "GridPreviewResult": GridPreviewResult,
            "read_wind_bounds": read_wind_bounds,
            "render_region_map": render_region_map,
            "scale_nested_region": scale_nested_region,
            "visualize_grid": visualize_grid,
        }[name]
    if name in {"PipelineResult", "run_pipeline", "run_prepare_forcing"}:
        from .preprocessing_workflow import PipelineResult, run_pipeline, run_prepare_forcing

        return {
            "PipelineResult": PipelineResult,
            "run_pipeline": run_pipeline,
            "run_prepare_forcing": run_prepare_forcing,
        }[name]
    raise AttributeError(name)
