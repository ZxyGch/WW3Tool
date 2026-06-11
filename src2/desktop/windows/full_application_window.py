"""Compatibility exports for the src2 desktop shell."""

from __future__ import annotations

from typing import Any


class DesktopSurfaceDependencyError(RuntimeError):
    """Raised when desktop dependencies are missing."""


def create_full_application_window():
    from .preprocessing_window import create_preprocessing_window

    return create_preprocessing_window()


def select_initial_work_directory(window: Any) -> bool:
    """Prompt for a work directory on startup. Returns False if the user cancels."""
    from .work_folder_dialog import WorkFolderDialog

    dialog = WorkFolderDialog(parent=window, is_startup=True)
    if dialog.exec() != dialog.DialogCode.Accepted or not dialog.selected_folder:
        return False
    if hasattr(window, "set_work_directory"):
        window.set_work_directory(dialog.selected_folder)
    return True
