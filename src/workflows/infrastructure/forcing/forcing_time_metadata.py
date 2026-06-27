"""WW3 ``ww3_prnc`` 强迫场时间轴元数据检测与修复。

CMEMS / ERA5 等 CF-1.11 NetCDF-4 文件常把 ``time:units`` / ``time:calendar`` 存为
NetCDF-4 **string** 类型属性；WW3 Fortran 端按经典 **char** 属性读取，会报
``calendar ATTRIBUTE NOT DEFINED`` 与 ``PREMATURE END OF TIME ATTRIBUTE``。

本模块在 Step 1 归一化前检测上述问题，并在写出时强制使用 WW3 可读的属性格式。
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from typing import Callable, List, Optional, Sequence

from ...support.translations import tr

_WW3_ALLOWED_CALENDARS = frozenset({"standard", "gregorian"})
_WW3_TIME_UNITS_RE = re.compile(
    r"^(seconds|minutes|hours|days)\s+since\s+"
    r"\d{4}-\d{1,2}-\d{1,2}\s+\d{1,2}:\d{1,2}:\d{1,2}\s*$",
    re.IGNORECASE,
)
_NC_STRING_TIME_ATTR_RE = re.compile(
    r"^\s*string\s+\w+:(units|calendar)\s*=",
    re.MULTILINE,
)
_TIME_CANDIDATES = ("valid_time", "time", "Time", "TIME", "t", "MT", "mt")


@dataclass(frozen=True)
class TimeMetadataIssue:
    """单条 WW3 时间元数据兼容性问题。"""

    code: str
    detail: str = ""


def pick_time_variable_name(dataset) -> Optional[str]:
    """在已打开的 NetCDF 数据集中解析时间变量名。"""
    for name in _TIME_CANDIDATES:
        if name in dataset.variables:
            return name
    return None


def has_nc_string_time_attributes(file_path: str) -> bool:
    """用 ``ncdump -h`` 检测 ``time:units/calendar`` 是否为 NetCDF-4 string 属性。"""
    if not shutil.which("ncdump"):
        return False
    try:
        out = subprocess.check_output(
            ["ncdump", "-h", file_path],
            text=True,
            stderr=subprocess.DEVNULL,
            errors="replace",
        )
    except (OSError, subprocess.CalledProcessError):
        return False
    return bool(_NC_STRING_TIME_ATTR_RE.search(out))


def audit_time_metadata_for_ww3(
    file_path: str,
    *,
    time_name: Optional[str] = None,
) -> List[TimeMetadataIssue]:
    """检查强迫场 NetCDF 的 ``time`` 元数据是否可被 WW3 ``ww3_prnc`` 读取。"""
    from netCDF4 import Dataset

    issues: List[TimeMetadataIssue] = []

    if has_nc_string_time_attributes(file_path):
        issues.append(
            TimeMetadataIssue(
                "nc_string_attr",
                "time:units/calendar stored as NetCDF-4 string",
            )
        )

    with Dataset(file_path, "r") as ds:
        resolved_time = time_name or pick_time_variable_name(ds)
        if not resolved_time:
            issues.append(TimeMetadataIssue("missing_time_var", ""))
            return issues

        time_var = ds.variables[resolved_time]
        units = getattr(time_var, "units", None)
        calendar = getattr(time_var, "calendar", None)

        if not units or not str(units).strip():
            issues.append(TimeMetadataIssue("missing_units", ""))
        elif not _WW3_TIME_UNITS_RE.match(str(units).strip()):
            issues.append(TimeMetadataIssue("invalid_units", str(units).strip()))

        if not calendar or not str(calendar).strip():
            issues.append(TimeMetadataIssue("missing_calendar", ""))
        elif str(calendar).strip().lower() not in _WW3_ALLOWED_CALENDARS:
            issues.append(
                TimeMetadataIssue("unsupported_calendar", str(calendar).strip())
            )

    return issues


def time_metadata_needs_ww3_fix(
    file_path: str,
    *,
    time_name: Optional[str] = None,
) -> bool:
    """是否存在需要重写的 WW3 时间元数据问题。"""
    return bool(audit_time_metadata_for_ww3(file_path, time_name=time_name))


def normalize_time_units_for_ww3(units: str) -> str:
    """把 ``since YYYY-MM-DD`` 补全为 ``since YYYY-MM-DD 00:00:00``。"""
    value = (units or "").strip()
    if not value:
        return value
    match = re.match(
        r"^(\S+\s+since\s+\d{4}-\d{1,2}-\d{1,2})$",
        value,
        re.IGNORECASE,
    )
    if match:
        return f"{match.group(1)} 00:00:00"
    return value


def normalize_calendar_for_ww3(calendar: Optional[str]) -> str:
    """把非 WW3 支持的 calendar 映射为 ``gregorian``。"""
    value = (calendar or "gregorian").strip().lower()
    if value in _WW3_ALLOWED_CALENDARS:
        return value
    return "gregorian"


def format_time_metadata_issue_logs(
    issues: Sequence[TimeMetadataIssue],
    *,
    log: Optional[Callable[[str], None]] = None,
) -> List[str]:
    """将检测结果格式化为可写入日志的文本行。"""
    lines: List[str] = []
    for issue in issues:
        if issue.code in {"nc_string_attr", "invalid_units"}:
            continue
        if issue.code == "missing_units":
            text = tr(
                "forcing_time_issue_missing_units",
                "⚠️ time 变量缺少 units 属性",
            )
        elif issue.code == "missing_calendar":
            text = tr(
                "forcing_time_issue_missing_calendar",
                "⚠️ time 变量缺少 calendar 属性（WW3 需要 standard 或 gregorian）",
            )
        elif issue.code == "unsupported_calendar":
            text = tr(
                "forcing_time_issue_unsupported_calendar",
                "⚠️ time:calendar={detail} 不被 WW3 支持，将改写为 gregorian",
            ).format(detail=issue.detail)
        elif issue.code == "missing_time_var":
            text = tr(
                "forcing_time_issue_missing_time_var",
                "⚠️ 未找到时间变量",
            )
        else:
            text = issue.detail or issue.code
        lines.append(text)
        if log is not None:
            log(text)
    return lines
