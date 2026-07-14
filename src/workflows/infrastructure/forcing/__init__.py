"""WW3 Step 2 强迫场导入基础设施包。

[EN] WW3 Step 2 forcing field import infrastructure package.

本包负责 NetCDF 强迫场文件的 I/O、变量检测、路径命名与单遍标准化归一化，
为应用层 ``forcing_preparation`` 等模块提供可复用的底层能力。

[EN] This package handles I/O, variable detection, path naming, and single-pass normalization
for NetCDF forcing files, providing reusable low-level capabilities for
application-layer modules such as ``forcing_preparation``.

主要子模块：
- ``file_path_manager``：按场类型组合生成/解析工作目录内的标准文件名；
- ``variable_detector``：检测 wind/current/level/ice 四类 WW3 强迫变量；
- ``file_service``：复制/移动文件，调用归一化服务完成坐标标准化与变量重命名；
- ``forcing_normalize_service``：单遍归一化所有强迫场坐标、变量名与时间单位，生成 WW3 可读的 NetCDF；
- ``merge_service``：分析并合并多个 NetCDF 强迫场文件，支持时间拼接与不同场合并；
- ``use_cases``：封装 Step 2 导入、扫描工作目录等编排入口。

[EN] Main submodules:
- ``file_path_manager``: Generate/parse standard filenames within the working directory based on field type combinations;
- ``variable_detector``: Detect wind/current/level/ice WW3 forcing variables;
- ``file_service``: Copy/move files, delegating normalization to the forcing normalize service;
- ``forcing_normalize_service``: Single-pass normalization of all forcing field coordinates, variable names, and time units into WW3-readable NetCDF;
- ``merge_service``: Analyze and merge NetCDF forcing files by time or by distinct forcing fields;
- ``use_cases``: Orchestration entry points for Step 2 import, working directory scanning, etc.
"""
