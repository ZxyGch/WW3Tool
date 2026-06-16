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
