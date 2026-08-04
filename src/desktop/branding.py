"""Application branding assets (window / title bar icon)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PyQt6.QtGui import QIcon

from ._repo_root import repo_root

LOGO_PATH = repo_root() / "public" / "resource" / "logo.png"


def load_logo_icon() -> QIcon | None:
    if not LOGO_PATH.is_file():
        return None
    icon = QIcon(str(LOGO_PATH))
    return icon if not icon.isNull() else None


def apply_window_logo(window: Any) -> None:
    """Set app logo on the window and FluentTitleBar icon label."""
    icon = load_logo_icon()
    if icon is None:
        return
    window.setWindowIcon(icon)
    title_bar = getattr(window, "titleBar", None)
    if title_bar is not None and hasattr(title_bar, "setIcon"):
        title_bar.setIcon(icon)
