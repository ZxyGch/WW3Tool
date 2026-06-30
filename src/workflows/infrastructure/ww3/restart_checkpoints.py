"""扫描工作目录中的 WW3 restart checkpoint（仅运行时使用）。"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from pathlib import Path


_CHECKPOINT_NAME = re.compile(r"^(\d{8})\.(\d{6})\.restart\.")
_RESTART_TIME = re.compile(r"^(\d{8})\s+(\d{6})$")
_RESTART_TIME_LOOSE = re.compile(r"^(\d{8})(?:\s+(\d{6}))?$")
_NUMBERED_RESTART = re.compile(r"^restart(\d+)\.ww3$", re.IGNORECASE)
_NML_RESTART_SCHEDULE = re.compile(
    r"(?:DATE|ALLDATE)%RESTART\s*=\s*'(\d{8}\s+\d{6})'\s*'(\d+)'",
    re.IGNORECASE,
)


def normalize_restart_time(value: str | None) -> str | None:
    """将 ``YYYYMMDD`` 或 ``YYYYMMDD HHMMSS`` 规范为 ``YYYYMMDD HHMMSS``。"""
    text = str(value or "").strip()
    if not text or text.lower() == "null":
        return None
    match = _RESTART_TIME_LOOSE.match(text)
    if not match:
        return None
    return f"{match.group(1)} {match.group(2) or '000000'}"


def checkpoint_time_from_path(path: Path) -> str | None:
    """从 ``YYYYMMDD.HHMMSS.restart.*`` 文件名解析 ``YYYYMMDD HHMMSS``。"""
    match = _CHECKPOINT_NAME.match(path.name)
    if not match:
        return None
    return f"{match.group(1)} {match.group(2)}"


def numbered_restart_index(path: Path) -> int | None:
    match = _NUMBERED_RESTART.match(path.name)
    if not match:
        return None
    return int(match.group(1))


def latest_checkpoint(directory: Path, suffix: str = "ww3") -> Path | None:
    """返回目录内最新的带时间戳 restart checkpoint。"""
    if not directory.is_dir():
        return None
    candidates = [p for p in directory.glob(f"*.restart.{suffix}") if checkpoint_time_from_path(p)]
    if not candidates:
        return None
    return sorted(candidates, key=lambda p: p.name)[-1]


def latest_numbered_restart(directory: Path) -> Path | None:
    """返回目录内编号最大的 ``restartNNN.ww3``。"""
    if not directory.is_dir():
        return None
    best: tuple[int, Path] | None = None
    for path in directory.glob("restart*.ww3"):
        index = numbered_restart_index(path)
        if index is None:
            continue
        if best is None or index > best[0]:
            best = (index, path)
    return best[1] if best else None


def parse_restart_schedule_from_nml(nml_path: Path) -> tuple[str, int] | None:
    """从 ``ww3_shel.nml`` / ``ww3_multi.nml`` 解析 ``DATE%RESTART`` 的 START 与 STRIDE（秒）。"""
    if not nml_path.is_file():
        return None
    for line in nml_path.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("!"):
            continue
        match = _NML_RESTART_SCHEDULE.search(line)
        if not match:
            continue
        stride = int(match.group(2))
        if stride <= 0:
            continue
        return match.group(1), stride
    return None


def parse_restart_schedule(workdir: Path, nml_path: Path | None = None) -> tuple[str, int] | None:
    """优先读 nml 的 ``DATE%RESTART``；失败时回退 ``params.yml`` 的 ``start_date`` + ``output_step``。"""
    nml = nml_path or workdir / "ww3_shel.nml"
    schedule = parse_restart_schedule_from_nml(nml)
    if schedule is not None:
        return schedule
    params_path = workdir / "params.yml"
    if not params_path.is_file():
        return None
    try:
        import yaml

        raw = yaml.safe_load(params_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return None
    ww3 = raw.get("ww3") if isinstance(raw, dict) else {}
    restart = (ww3 or {}).get("restart") if isinstance(ww3, dict) else {}
    start_date = str((ww3 or {}).get("start_date") or "").strip()
    output_step = str(
        (restart or {}).get("output_step")
        or (ww3 or {}).get("output_step")
        or ""
    ).strip()
    if not (start_date.isdigit() and len(start_date) == 8 and output_step.isdigit()):
        return None
    stride = int(output_step)
    if stride <= 0:
        return None
    return f"{start_date} 000000", stride


def restart_time_for_numbered_index(start_time: str, stride_seconds: int, index: int) -> str:
    start = datetime.strptime(start_time, "%Y%m%d %H%M%S")
    moment = start + timedelta(seconds=stride_seconds * index)
    return moment.strftime("%Y%m%d %H%M%S")


def numbered_restart_for_time(
    directory: Path,
    restart_time: str,
    *,
    nml_path: Path | None = None,
) -> Path | None:
    """按 ``restart_time`` 与 nml 中 RESTART 步长，匹配 ``restartNNN.ww3``。"""
    resolved = normalize_restart_time(restart_time)
    if not resolved:
        return None
    schedule = parse_restart_schedule(directory, nml_path or directory / "ww3_shel.nml")
    if schedule is None:
        return None
    start_time, stride = schedule
    target = datetime.strptime(resolved, "%Y%m%d %H%M%S")
    start = datetime.strptime(start_time, "%Y%m%d %H%M%S")
    delta = int((target - start).total_seconds())
    if delta < 0 or delta % stride != 0:
        return None
    index = delta // stride
    if index <= 0:
        return None
    candidate = directory / f"restart{index:03d}.ww3"
    if candidate.is_file():
        return candidate
    matches = [p for p in directory.glob(f"restart{index}.ww3")]
    return matches[0] if matches else None


def find_checkpoint(directory: Path, restart_time: str, suffix: str = "ww3") -> Path | None:
    """按 ``YYYYMMDD HHMMSS`` 查找对应的 checkpoint 文件。"""
    resolved = normalize_restart_time(restart_time)
    if not resolved or not directory.is_dir():
        return None
    match = _RESTART_TIME.match(resolved)
    if not match:
        return None
    pattern = f"{match.group(1)}.{match.group(2)}.restart.{suffix}"
    matches = sorted(directory.glob(pattern))
    return matches[0] if matches else None


def resolve_restart_file_name(restart_file: str | None) -> str | None:
    """仅接受工作目录内的 restart 文件名（禁止路径穿越）。"""
    name = str(restart_file or "").strip()
    if not name:
        return None
    if "/" in name or "\\" in name or name in {".", ".."}:
        raise ValueError(f"restart_file 必须是工作目录内的文件名: {name!r}")
    return name


def resolve_regular_restart_source(
    workdir: Path,
    *,
    pick_latest: bool,
    restart_time: str | None,
    restart_file: str | None,
    nml_path: Path | None = None,
) -> tuple[Path, str]:
    """解析单层热启动应复制的 checkpoint 与积分起点时刻。"""
    nml = nml_path or workdir / "ww3_shel.nml"
    if pick_latest:
        checkpoint = latest_checkpoint(workdir, "ww3")
        if checkpoint is not None:
            resolved_time = checkpoint_time_from_path(checkpoint)
            if resolved_time:
                return checkpoint, resolved_time
        numbered = latest_numbered_restart(workdir)
        if numbered is not None:
            index = numbered_restart_index(numbered)
            schedule = parse_restart_schedule(workdir, nml)
            if index is not None and schedule is not None:
                resolved_time = restart_time_for_numbered_index(schedule[0], schedule[1], index)
                return numbered, resolved_time
        raise FileNotFoundError("Auto Latest: no timestamped or numbered restart checkpoint found")

    resolved_time = normalize_restart_time(restart_time)
    if not resolved_time:
        raise ValueError(
            "Restart mode requires restart_time (YYYYMMDD or YYYYMMDD HHMMSS) when Auto Latest is disabled"
        )

    file_name = resolve_restart_file_name(restart_file)
    if file_name:
        source = workdir / file_name
        if not source.is_file():
            raise FileNotFoundError(f"Restart file not found in workdir: {file_name}")
        return source, resolved_time

    checkpoint = find_checkpoint(workdir, resolved_time, "ww3")
    if checkpoint is not None:
        return checkpoint, resolved_time

    numbered = numbered_restart_for_time(workdir, resolved_time, nml_path=nml)
    if numbered is not None:
        return numbered, resolved_time

    raise FileNotFoundError(
        "Manual restart: specify restart_file, add a timestamped checkpoint, "
        f"or ensure restartNNN.ww3 matches restart_time ({resolved_time})"
    )
