"""外部工具与 WW3 准备流程的适配器层。

本包将 ``PipelineConfig`` 等域模型桥接到具体实现：

- ``generate_grid``：调用 meshgen 生成 structured/SMC/非结构网格；
- ``prepare_ww3_files``：无 GUI 环境下生成 WW3 namelist 与运行脚本。

通过 ``__getattr__`` 延迟导入，避免 CLI 启动时不必要的重依赖加载。

[EN] Adapter layer between external tools and the WW3 preparation pipeline.

This package bridges domain models such as ``PipelineConfig`` to concrete implementations:

- ``generate_grid``: invokes meshgen to produce structured/SMC/unstructured grids;
- ``prepare_ww3_files``: generates WW3 namelist and run scripts in a headless (no-GUI) environment.

Lazy imports via ``__getattr__`` avoid unnecessary heavy dependency loading at CLI startup.
"""
