"""在子进程中运行 matplotlib 绘图 worker，避免阻塞桌面 UI 主线程。

绘图 worker 约定签名::

    worker(*args, log_queue, result_queue, **kwargs)

与 ``infrastructure/plot/*`` 及 ``queue_bridge.ImmediateQueue`` 路径一致，
但子进程执行可释放 GIL，并与 Qt 事件循环隔离。
"""

from __future__ import annotations

import multiprocessing
import time
from queue import Empty
from typing import Any, Callable, Optional


def _dispatch_log(on_log: Callable[[str], None] | None, msg: Any) -> None:
    if on_log is None:
        return
    if isinstance(msg, tuple) and len(msg) == 2 and msg[0] == "__UPDATE__":
        on_log(str(msg[1]))
        return
    on_log(str(msg))


def run_subprocess_worker(
    target: Callable[..., None],
    args: tuple = (),
    *,
    on_log: Optional[Callable[[str], None]] = None,
    poll_interval: float = 0.05,
    join_timeout: float = 3600.0,
) -> list[Any]:
    """在子进程中执行 ``target(*args, log_queue, result_queue)`` 并收集结果。

    Args:
        target: Worker 入口；最后两个参数由本函数注入队列。
        args: 传给 worker 的前置位置参数。
        on_log: 日志回调；收到 ``"__DONE__"`` 时仅标记结束，不回调。
        poll_interval: 轮询队列间隔（秒）。
        join_timeout: ``Process.join`` 超时（秒）。

    Returns:
        ``result_queue`` 上收到的全部对象列表。
    """
    ctx = multiprocessing.get_context("spawn")
    log_queue = ctx.Queue()
    result_queue = ctx.Queue()
    process = ctx.Process(target=target, args=(*args, log_queue, result_queue))
    process.start()

    results: list[Any] = []
    worker_done = False

    def _drain_queues() -> None:
        nonlocal worker_done
        while True:
            try:
                msg = log_queue.get_nowait()
            except Empty:
                break
            if msg == "__DONE__":
                worker_done = True
                continue
            _dispatch_log(on_log, msg)

        while True:
            try:
                results.append(result_queue.get_nowait())
            except Empty:
                break

    try:
        while True:
            _drain_queues()
            if worker_done and not process.is_alive():
                _drain_queues()
                break
            if not process.is_alive():
                _drain_queues()
                break
            time.sleep(poll_interval)
    finally:
        process.join(timeout=join_timeout)
        if process.is_alive():
            process.terminate()
            process.join(timeout=5)
        _drain_queues()

    return results


def _plot_worker_entry(
    payload: tuple[Callable[..., None], tuple, dict[str, Any]],
    log_queue,
    result_queue,
) -> None:
    """子进程入口（模块级，便于 multiprocessing spawn 序列化）。"""
    target, args, kwargs = payload
    target(*args, log_queue, result_queue, **kwargs)


def run_plot_worker(
    target: Callable[..., None],
    args: tuple,
    *,
    kwargs: Optional[dict[str, Any]] = None,
    on_log: Optional[Callable[[str], None]] = None,
) -> Any:
    """运行绘图 worker 并返回 ``result_queue`` 上最后一个对象（若有）。"""
    results = run_subprocess_worker(
        _plot_worker_entry,
        ((target, args, kwargs or {}),),
        on_log=on_log,
    )
    return results[-1] if results else None
