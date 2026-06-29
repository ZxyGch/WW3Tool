"""多方案路径映射解析与写回（slurm.server_st、local_run.local_st 等）。

仅支持多方案格式（必须含 ``use``）::

    server_st:
      use: ST2
      ST2: /path/to/exe
      ST4: /path/to/exe2
"""

from __future__ import annotations

from typing import Any, Mapping

PRESET_META_KEYS = frozenset({"use", "active"})


def parse_named_path_preset_block(
    value: Any,
    *,
    path: str,
) -> tuple[str, dict[str, str]]:
    """解析命名路径预设块，返回 (当前 use, 方案名→路径)。"""
    if value is None:
        raise ValueError(f"{path} 不能为空")
    if not isinstance(value, dict):
        raise ValueError(f"{path} 必须是映射对象（use + 方案名: 路径）")

    active: str | None = None
    schemes: dict[str, str] = {}
    for key, raw in value.items():
        name = str(key).strip()
        if not name:
            raise ValueError(f"{path} 的方案名不能为空")
        if name in PRESET_META_KEYS:
            active = str(raw).strip()
            continue
        executable_dir = str(raw).strip()
        if not executable_dir:
            raise ValueError(f"{path}.{name} 路径不能为空")
        schemes[name] = executable_dir.rstrip("/")

    if not schemes:
        raise ValueError(f"{path} 至少应定义一个方案（方案名: 路径）")
    if not active:
        raise ValueError(f"{path} 必须指定 use: <方案名>")
    if active not in schemes:
        raise ValueError(f"{path}.use 未知方案名：{active}；须在 {path} 中定义")

    return active, schemes


def serialize_named_path_preset_block(
    active: str,
    schemes: Mapping[str, str],
) -> dict[str, str]:
    """将方案映射写回 YAML（始终含 use）。"""
    active_name = str(active).strip()
    body: dict[str, str] = {}
    for name, executable_dir in schemes.items():
        key = str(name).strip()
        if not key or key in PRESET_META_KEYS:
            continue
        path = str(executable_dir).strip().rstrip("/")
        if path:
            body[key] = path
    if not body:
        raise ValueError("路径预设无有效方案可写回")
    if active_name not in body:
        raise ValueError(f"use 方案名 {active_name} 不在预设列表中")
    return {"use": active_name, **body}
