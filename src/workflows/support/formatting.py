"""Shared human-readable formatting helpers."""

from __future__ import annotations


def format_file_size(size: int | float) -> str:
    """Format byte count as B / KB / MB / GB.

    [EN] Format byte count into a human-readable file size string.
    """
    value = float(size)
    if value < 1024:
        return f"{int(value)} B"
    if value < 1024 * 1024:
        return f"{value / 1024:.2f} KB"
    if value < 1024 * 1024 * 1024:
        return f"{value / (1024 * 1024):.2f} MB"
    return f"{value / (1024 * 1024 * 1024):.2f} GB"


def format_key_value_lines(entries, *, indent: str = "    ", arrow: str = "→") -> str:
    """把 ``key=value`` 条目排成对齐的多行。

    启动时汇报被置空的路径原本是用 ``", "`` 拼成一行的，而这些值是绝对路径，
    连起来能有好几百字符，终端里裹成一团没法看。

    [EN] Lay out ``key=value`` entries one per line, keys aligned.  Joining
    them with commas produced a single unreadable line, since the values are
    absolute paths.
    """
    parsed = []
    for entry in entries:
        text = str(entry)
        key, sep, value = text.partition("=")
        parsed.append((key.strip(), value.strip() if sep else ""))
    if not parsed:
        return ""
    width = max(len(key) for key, _ in parsed)
    lines = []
    for key, value in parsed:
        if value and value.lower() != "null":
            lines.append(f"{indent}{key.ljust(width)} {arrow} {value}")
        else:
            lines.append(f"{indent}{key}")
    return "\n".join(lines)
