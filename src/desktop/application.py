"""Desktop startup for the workflow-backed application."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


def _select_initial_work_directory(window: Any) -> bool:
    """Prompt for a work directory on startup. Returns False if the user cancels."""
    from .windows.work_folder_dialog import WorkFolderDialog

    dialog = WorkFolderDialog(parent=window, is_startup=True)
    if dialog.exec() != dialog.DialogCode.Accepted or not dialog.selected_folder:
        return False
    if hasattr(window, "set_work_directory"):
        window.set_work_directory(dialog.selected_folder)
    return True


def create_window():
    from .windows.preprocessing_window import create_preprocessing_window

    return create_preprocessing_window()


def main(argv: list[str] | None = None) -> int:
    try:
        from PyQt6.QtGui import QIcon
        from PyQt6.QtWidgets import QApplication
    except ImportError as exc:
        raise SystemExit(
            "无法启动桌面界面：请先安装 PyQt6 依赖 "
            "(python3 -m pip install -r src/requirements.txt)"
        ) from exc

    # [EN] Validate root params.yml paths at startup (same as CLI/shell).
    # Incompatible or non-existent paths are auto-corrected before any config is loaded.
    try:
        from workflows.infrastructure.runtime_config import sanitize_root_params_paths
        sanitize_root_params_paths()
    except Exception:
        pass

    arguments = [sys.argv[0], *(argv if argv is not None else sys.argv[1:])]
    app = QApplication(arguments)
    icon = Path(__file__).resolve().parents[2] / "public" / "resource" / "logo.png"
    if icon.exists():
        app.setWindowIcon(QIcon(str(icon)))

    window = create_window()
    window.show()
    if not _select_initial_work_directory(window):
        return 0
    return app.exec()
