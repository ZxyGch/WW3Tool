"""进程内队列桥接：以同步方式调用多进程风格的 worker。

本模块属于 ``support/`` 支撑层。绘图 worker 最初为多进程设计，通过
``log_queue`` 与 ``result_queue``（``multiprocessing.Queue``）通信。

CLI 在同进程内直接调用 worker 时，``queue.SimpleQueue`` 虽可用，
但执行期间无人消费队列，日志往往要等 worker 全部结束后才可见。
``ImmediateQueue`` 在每次 ``put()`` 时立即触发回调，实现实时进度输出，
同时内部仍缓存条目，供 ``get_nowait()`` / ``empty()`` 读取结果。

用法示例::

    log_q = ImmediateQueue(callback=logger.log)
    result_q = ImmediateQueue()
    _make_wave_maps_worker(folder, step, log_q, result_q, ...)
    result = result_q.get_nowait() if not result_q.empty() else None

主要消费者：
- ``application/plot_*.py``、``application/match_*.py`` 等 CLI 绘图/匹配用例
"""

from __future__ import annotations

from collections import deque
from typing import Any, Callable, Optional


class _EmptyError(Exception):
    """队列为空时 ``get`` / ``get_nowait`` 抛出的内部异常。"""


class ImmediateQueue:
    """``put()`` 时立即调用可选回调的内存队列。

    接口与 ``infrastructure/plot/`` 下 worker 期望的
    ``log_queue`` / ``result_queue`` 兼容。

    关键属性：
    - ``_callback``：``put`` 时同步调用的处理函数（如 ``logger.log``）
    - ``_items``：FIFO  deque，供后续 ``get`` 读取
    """

    def __init__(self, callback: Optional[Callable[[Any], None]] = None) -> None:
        """初始化队列。

        Args:
            callback: 每次 ``put`` 时调用的函数；回调异常会被静默忽略。
        """
        self._callback = callback
        self._items: deque = deque()

    def put(self, item: Any) -> None:
        """入队并在有回调时立即分发。

        Args:
            item: 日志字符串或 worker 结果对象。
        """
        if self._callback is not None:
            try:
                self._callback(item)
            except Exception:
                pass
        self._items.append(item)

    def get_nowait(self) -> Any:
        """非阻塞取出队首元素。

        Returns:
            队首元素。

        Raises:
            _EmptyError: 队列为空。
        """
        if not self._items:
            raise _EmptyError("queue is empty")
        return self._items.popleft()

    def get(self, block: bool = True, timeout: Optional[float] = None) -> Any:
        """取出队首元素（接口兼容 ``multiprocessing.Queue``，忽略 block/timeout）。

        Returns:
            队首元素。

        Raises:
            _EmptyError: 队列为空。
        """
        if not self._items:
            raise _EmptyError("queue is empty")
        return self._items.popleft()

    def empty(self) -> bool:
        """队列是否无待读元素。"""
        return len(self._items) == 0
