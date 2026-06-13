"""application 与 interfaces 层共用的支撑工具。

本包属于 ``support/`` 层，提供日志、翻译等横切能力，可被 interfaces、
application 直接引用，但不反向依赖业务用例。

导出符号：
- ``CoreLogger`` / ``LogCallback``：统一日志接口
- ``tr``：翻译回退函数

[EN] Support utilities shared by the application and interfaces layers.

This package belongs to the ``support/`` layer and provides cross-cutting
capabilities such as logging and translation. It can be imported directly
by interfaces and application layers but never depends on business use cases.

Exported symbols:
- ``CoreLogger`` / ``LogCallback``: unified logging interface
- ``tr``: translation fallback function
"""

from .logging import CoreLogger, LogCallback
from .translations import tr

__all__ = ["CoreLogger", "LogCallback", "tr"]
