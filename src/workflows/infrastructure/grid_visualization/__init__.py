"""WW3 网格可视化子模块（worker 与描述文件解析）。

包含：

- ``worker``：在独立子进程中用 matplotlib/cartopy 绘制 structured/SMC/非结构网格图；
- ``rect_grid_desc_parse``：解析 ``grid.meta`` / ``grid.nml`` 中的 RECT/CURV 几何；
- ``structured_grid_paths``：定位工作目录内应使用的网格描述文件路径。

[EN] WW3 grid visualization sub-package (worker and description file parsing).

Contains:

- ``worker``: draws structured/SMC/unstructured grid plots using matplotlib/cartopy in an isolated subprocess;
- ``rect_grid_desc_parse``: parses RECT/CURV geometry from ``grid.meta`` / ``grid.nml``;
- ``structured_grid_paths``: locates the grid description file paths to be used within the working directory.
"""
