"""WW3Tool 无界面预处理工作流包。

本包是 CLI（``run.py``）与 Desktop（``src/desktop/``）共用的核心业务层，
编排 forcing、grid、WW3 namelist、绘图与远程运维等用例。

为避免 ``print-example`` 等轻量命令在安装 NetCDF/Grid/Qt 全量依赖前失败，
公共符号通过 ``__getattr__`` 延迟导入，不在包加载时拉起重依赖栈。

主要消费者：
- ``run.py``：统一入口（CLI 子命令分发到这里）
- 测试与外部脚本：``from workflows import load_pipeline_config, run_pipeline``

导出符号（均为懒加载）：
- 配置：``ConfigError``、``PipelineConfig``、``load_pipeline_config``、``validate_pipeline_config``
- 预处理：``PipelineResult``、``run_pipeline``、``run_prepare_forcing``
- 网格：``GridGenerationResult``、``run_generate_grid``

[EN] Headless preprocessing workflow package for WW3Tool.

This package is the core business layer shared by the CLI (``run.py``) and
Desktop (``src/desktop/``) front-ends, orchestrating use cases for forcing, grid,
WW3 namelist, plotting, and remote operations.

To prevent lightweight commands such as ``print-example`` from failing before
NetCDF/Grid/Qt full dependencies are installed, public symbols are lazily
imported via ``__getattr__`` so that heavy dependency stacks are not pulled in
at package load time.

Main consumers:
- ``run.py``: unified entry point (CLI subcommands dispatch here)
- Tests and external scripts: ``from workflows import load_pipeline_config, run_pipeline``

Exported symbols (all lazy-loaded):
- Configuration: ``ConfigError``, ``PipelineConfig``, ``load_pipeline_config``, ``validate_pipeline_config``
- Preprocessing: ``PipelineResult``, ``run_pipeline``, ``run_prepare_forcing``
- Grid: ``GridGenerationResult``, ``run_generate_grid``
"""

__all__ = [
    "ConfigError",
    "PipelineConfig",
    "PipelineResult",
    "GridGenerationResult",
    "load_pipeline_config",
    "run_pipeline",
    "run_prepare_forcing",
    "run_generate_grid",
    "validate_pipeline_config",
]


def __getattr__(name):
    """按名称延迟导入公共 API，避免包初始化时加载重型依赖。

    Args:
        name: ``__all__`` 中声明的符号名。

    Returns:
        对应的类或 callable。

    Raises:
        AttributeError: ``name`` 不在公共 API 中。

    [EN] Lazily import a public API symbol by name to avoid loading heavy
    dependencies during package initialization.

    Args:
        name: Symbol name declared in ``__all__``.

    Returns:
        The corresponding class or callable.

    Raises:
        AttributeError: ``name`` is not part of the public API.
    """
    if name in {"ConfigError", "load_pipeline_config"}:
        from .application.configuration import ConfigError, load_pipeline_config

        return {"ConfigError": ConfigError, "load_pipeline_config": load_pipeline_config}[name]
    if name == "PipelineConfig":
        from .domain.config_models import PipelineConfig

        return PipelineConfig
    if name in {"PipelineResult", "run_pipeline", "run_prepare_forcing", "validate_pipeline_config"}:
        from .application.preprocessing_workflow import (
            PipelineResult,
            run_pipeline,
            run_prepare_forcing,
        )
        from .application.configuration import validate_pipeline_config

        return {
            "PipelineResult": PipelineResult,
            "run_pipeline": run_pipeline,
            "run_prepare_forcing": run_prepare_forcing,
            "validate_pipeline_config": validate_pipeline_config,
        }[name]
    if name in {"GridGenerationResult", "run_generate_grid"}:
        from .application.grid_preparation import GridGenerationResult, run_generate_grid

        return {
            "GridGenerationResult": GridGenerationResult,
            "run_generate_grid": run_generate_grid,
        }[name]
    raise AttributeError(name)
