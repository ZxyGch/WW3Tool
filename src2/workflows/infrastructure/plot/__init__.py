"""WW3 结果绘图 Worker 基础设施包（无 GUI 依赖）。

包含 Jason-3 / NDBC 验证匹配、二维谱图、波高填色图与等值线图等子进程 Worker，
以及 NetCDF 网格坐标解析、三角网读取等公共辅助函数（``workers_utils``）。
供桌面端第八步绘图面板通过 ``multiprocessing`` 队列调用。
"""