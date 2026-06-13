"""application 与 interfaces 层共用的支撑工具。

本包属于 ``support/`` 层，提供日志、翻译等横切能力，可被 interfaces、
application 直接引用，但不反向依赖业务用例。

导出符号：
- ``CoreLogger`` / ``LogCallback``：统一日志接口
- ``tr``：翻译回退函数
"""

from .logging import CoreLogger, LogCallback
from .translations import tr

__all__ = ["CoreLogger", "LogCallback", "tr"]
