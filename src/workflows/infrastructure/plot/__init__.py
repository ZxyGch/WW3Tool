"""WW3 结果绘图 Worker 基础设施包（无 GUI 依赖）。

[EN] WW3 result plotting Worker infrastructure package (no GUI dependency).

包含 Jason-3 / NDBC 验证匹配、二维谱图、波高填色图与等值线图等子进程 Worker，
以及 NetCDF 网格坐标解析、三角网读取等公共辅助函数（``workers_utils``）。
供桌面端第八步绘图面板通过 ``multiprocessing`` 队列调用。

[EN] Contains subprocess Workers for Jason-3 / NDBC validation matching, 2D spectral plots,
wave height filled maps and contour maps, as well as common helper functions (``workers_utils``)
for NetCDF grid coordinate parsing and triangle mesh reading.
Invoked by the desktop Step 8 plotting panel via ``multiprocessing`` queues.
"""