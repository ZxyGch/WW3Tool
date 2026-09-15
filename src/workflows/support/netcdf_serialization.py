"""NetCDF4 / HDF5 访问全局串行化。

[EN] Global serialization of NetCDF4 / HDF5 access.

背景
----
HDF5 库默认不是线程安全的（Homebrew 及多数 wheel 均未开启
``H5_HAVE_THREADSAFE``）。多线程同时打开/遍历/关闭同一个（或不同）NetCDF
文件时，内部错误栈（H5E）与引用计数会发生内存损坏，表现为进程直接闪退
（SIGSEGV / SIGABRT），且没有任何 Python traceback。

GUI 中「选择强迫场文件」会让主线程（公共范围刷新 / 变量自动解析）与后台
线程（BackgroundRunner 执行文件概览）并发打开同一个 Dataset，正是崩溃现场。

本模块提供进程级 ``RLock`` 与配套上下文管理器：同一时刻仅一个线程持有锁并
操作 netCDF4，从根源上消除并发竞争。所有强迫场相关的 ``with Dataset(...)``
都应改用 :func:`serialized_dataset`。

用法
----
    from workflows.support.netcdf_serialization import serialized_dataset

    with serialized_dataset(path, "r") as ds:
        ...  # 整段代码处于全局锁内，线程安全

生命周期跨多个函数、无法用 with 的场景，可直接持有锁：

    from workflows.support.netcdf_serialization import nc_lock

    with nc_lock:
        ds = Dataset(path, "r")
        ...
        ds.close()

注意：锁是进程级的。绘图等独立子进程会各自初始化一把互不相干的锁，
不存在跨进程阻塞；单线程 CLI 完全无竞争，锁开销可忽略。

[EN] HDF5 is not thread-safe unless built with ``H5_HAVE_THREADSAFE``.
Concurrent open/iterate/close of NetCDF files from multiple threads corrupts
the internal error stack (H5E) and refcounts, crashing the process with no
Python traceback. The GUI "select forcing file" flow opens the same Dataset
from the main thread and a background thread at the same time -- exactly the
crash site. This module provides a process-wide RLock and a drop-in
context manager so only one thread touches netCDF4 at a time.
"""

from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Any, Iterator

# 进程级可重入全局锁：同一时刻仅一个线程允许操作 netCDF4。
# [EN] Process-wide reentrant lock: only one thread may touch netCDF4 at a time.
nc_lock = threading.RLock()


@contextmanager
def serialized_dataset(*args: Any, **kwargs: Any) -> Iterator[Any]:
    """线程安全的 Dataset 上下文管理器：与 ``with Dataset(...)`` 等价，额外持全局锁。

    [EN] Thread-safe Dataset context manager: same semantics as
    ``with Dataset(...)`` plus the global lock held for the whole block.
    """
    from netCDF4 import Dataset

    with nc_lock:
        ds = Dataset(*args, **kwargs)
        try:
            yield ds
        finally:
            ds.close()