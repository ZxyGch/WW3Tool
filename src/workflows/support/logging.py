"""CLI 与未来 UI 调用方共用的轻量日志适配器。

本模块属于 ``support/`` 支撑层，为 application 与 infrastructure 中的服务
提供统一的 ``log(message)`` 接口，既可写入内存缓冲，也可通过回调实时转发。

主要消费者：
- ``application/*`` 各用例（传入 ``print`` 或 ``CoreLogger`` 实例）
- ``infrastructure/plot/*`` 绘图 worker（经 ``ImmediateQueue`` 间接回调）

[EN] Lightweight logging adapter shared by CLI and future UI callers.

This module belongs to the ``support/`` layer and provides a unified
``log(message)`` interface for services in application and infrastructure.
It can buffer messages in memory or forward them in real time via callbacks.

Main consumers:
- ``application/*`` use cases (pass in ``print`` or a ``CoreLogger`` instance)
- ``infrastructure/plot/*`` plotting workers (indirect callback via ``ImmediateQueue``)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List, Optional


LogCallback = Callable[[str], None]


@dataclass
class CoreLogger:
    """兼容既有 WW3Tool 服务期望的最小日志器。

    关键字段：
    - ``callback``：可选的外部回调，每次 ``log`` 时同步调用
    - ``messages``：按时间顺序累积的全部日志文本，便于测试断言

    [EN] Minimal logger compatible with existing WW3Tool service expectations.

    Key fields:
    - ``callback``: optional external callback, invoked synchronously on each ``log`` call
    - ``messages``: all log texts accumulated in chronological order, convenient for test assertions
    """

    callback: Optional[LogCallback] = None
    messages: List[str] = field(default_factory=list)

    def log(self, message: str) -> None:
        """记录一条日志并可选地触发回调。

        Args:
            message: 日志文本，非字符串时会先 ``str()`` 转换。

        [EN] Record a log message and optionally trigger the callback.

        Args:
            message: Log text; will be converted via ``str()`` if not already a string.
        """
        text = str(message)
        self.messages.append(text)
        if self.callback is not None:
            self.callback(text)

    def __call__(self, message: str) -> None:
        """使实例可直接作为 ``log=logger`` 可调用对象使用。

        [EN] Allow the instance to be used directly as a ``log=logger`` callable.
        """
        self.log(message)
