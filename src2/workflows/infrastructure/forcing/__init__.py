"""WW3 Step 1 强迫场导入基础设施包。

本包负责 NetCDF 强迫场文件的 I/O、变量检测、路径命名、格式修复与风场归一化，
为应用层 ``forcing_preparation`` 等模块提供可复用的底层能力。

主要子模块：
- ``file_path_manager``：按场类型组合生成/解析工作目录内的标准文件名；
- ``variable_detector``：检测 wind/current/level/ice 四类 WW3 强迫变量；
- ``file_service``：复制/移动文件并修复时间轴、风场变量名等格式问题；
- ``wind_normalize_service``：将风场重排为 WW3 可读的 (time, lat, lon) 布局；
- ``use_cases``：封装 Step 1 导入、扫描工作目录等编排入口（历史命名保留 UseCase 后缀）。
"""
