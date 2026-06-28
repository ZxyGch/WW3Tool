"""NML 修改日志格式化 — 多行列出实际字段，等号对齐。

供 Step 4 各 nml 修改 Mixin 复用，与谱点 ww3_shel 日志风格一致。
"""
from __future__ import annotations

from collections.abc import Sequence

from ...support.translations import tr

Assignment = tuple[str, str]


def format_nml_assignments(
    assignments: Sequence[Assignment],
    *,
    blank_before_prefixes: Sequence[str] = (),
) -> str:
    """将 (字段名, 值) 列表格式化为对齐的多行文本。"""
    items = [(name.strip(), value.strip()) for name, value in assignments if name]
    if not items:
        return ""

    width = max(len(name) for name, _ in items)
    lines: list[str] = []
    prev_name = ""

    for name, value in items:
        if lines and blank_before_prefixes:
            if any(name.startswith(prefix) for prefix in blank_before_prefixes):
                if not any(prev_name.startswith(prefix) for prefix in blank_before_prefixes):
                    lines.append("")
        lines.append(f"  {name:<{width}} = {value}")
        prev_name = name

    return "\n".join(lines)


def format_nml_log_message(
    translation_key: str,
    default_template: str,
    assignments: Sequence[Assignment],
    *,
    blank_before_prefixes: Sequence[str] = (),
    **format_kwargs: object,
) -> str:
    """生成带对齐字段明细的 NML 修改日志。"""
    details = format_nml_assignments(
        assignments,
        blank_before_prefixes=blank_before_prefixes,
    )
    kwargs = {"details": details, **format_kwargs}
    return tr(translation_key, default_template).format(**kwargs)
