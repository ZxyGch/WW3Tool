"""冷/热启动有效积分窗口。"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from ...domain.config_models import PipelineConfig
from ..ww3.restart_checkpoints import normalize_restart_time, resolve_regular_restart_source
from .errors import BoundaryError
from ...support.translations import tr


def parse_ww3_date(value: str, *, end: bool = False) -> datetime:
    text = str(value or "").strip()
    if len(text) == 8 and text.isdigit():
        hhmmss = "235959" if end else "000000"
        text = f"{text} {hhmmss}"
    try:
        dt = datetime.strptime(text, "%Y%m%d %H%M%S")
    except ValueError as exc:
        raise BoundaryError(
            "BOUNDARY_TIME_COVERAGE",
            tr("boundary_date_unparsable", "无法解析日期 {value!r}").format(value=value),
        ) from exc
    return dt.replace(tzinfo=timezone.utc)


def effective_window(config: PipelineConfig, *, workdir: Path | None = None) -> tuple[datetime, datetime, str]:
    """返回 (start, end, init_mode)。热启动必须先解析实际 checkpoint。"""
    end = parse_ww3_date(config.ww3.end_date, end=True)
    if config.restart.mode != "restart":
        start = parse_ww3_date(config.ww3.start_date, end=False)
        return start, end, "cold"
    root = Path(workdir or config.workdir.path)
    if config.restart.pick_latest_checkpoint:
        try:
            _source, resolved = resolve_regular_restart_source(
                root,
                pick_latest=True,
                restart_time=None,
                restart_file=None,
                nml_path=root / "ww3_shel.nml",
            )
        except FileNotFoundError as exc:
            raise BoundaryError(
                "BOUNDARY_TIME_COVERAGE",
                tr("boundary_restart_needs_checkpoint", "热启动需要可用 checkpoint，禁止因边界缺失而改冷启动"),
                context={"workdir": str(root)},
                hints=[tr("boundary_hint_restart", "准备 restart 文件或改为冷启动")],
            ) from exc
        start = parse_ww3_date(resolved, end=False)
        return start, end, "restart"
    restart_time = normalize_restart_time(config.restart.restart_time)
    if not restart_time:
        raise BoundaryError(
            "BOUNDARY_TIME_COVERAGE",
            tr("boundary_restart_time_required", "关闭自动最新 checkpoint 时必须填写 restart_time"),
        )
    start = parse_ww3_date(restart_time, end=False)
    return start, end, "restart"


def format_ww3_time(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y%m%d %H%M%S")
