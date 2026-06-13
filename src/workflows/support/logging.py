"""CLI 与未来 UI 调用方共用的轻量日志适配器。

本模块属于 ``support/`` 支撑层，为 application 与 infrastructure 中的服务
提供统一的 ``log(message)`` 接口，既可写入内存缓冲，也可通过回调实时转发。

主要消费者：
- ``application/*`` 各用例（传入 ``print`` 或 ``CoreLogger`` 实例）
- ``infrastructure/plot/*`` 绘图 worker（经 ``ImmediateQueue`` 间接回调）
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
    """

    callback: Optional[LogCallback] = None
    messages: List[str] = field(default_factory=list)

    def log(self, message: str) -> None:
        """记录一条日志并可选地触发回调。

        Args:
            message: 日志文本，非字符串时会先 ``str()`` 转换。
        """
        text = str(message)
        self.messages.append(text)
        if self.callback is not None:
            self.callback(text)

    def __call__(self, message: str) -> None:
        """使实例可直接作为 ``log=logger`` 可调用对象使用。"""
        self.log(message)
