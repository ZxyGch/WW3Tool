"""
Facade for Step 1 state and compatibility helpers.
"""

from __future__ import annotations

import os
from typing import Iterable, Optional

from setting.config import load_config

from .state import FORCING_FIELD_ORDER, ForcingField, Step1Files, Step1State


class Step1Facade:
    """Owns Step 1 state and exposes a narrow mutation API."""

    def __init__(self) -> None:
        self._state = Step1State()
        self.reload_runtime_options()

    @property
    def state(self) -> Step1State:
        return self._state

    @property
    def files(self) -> Step1Files:
        return self._state.files

    def snapshot(self) -> Step1State:
        return self._state.copy()

    def reload_runtime_options(self) -> Step1State:
        try:
            config = load_config()
        except Exception:
            config = {}
        self._state.auto_associate = bool(config.get("FORCING_FIELD_AUTO_ASSOCIATE", True))
        self._state.process_mode = str(config.get("FORCING_FIELD_FILE_PROCESS_MODE", "copy") or "copy")
        return self._state

    def set_selected_folder(self, selected_folder: Optional[str]) -> None:
        if isinstance(selected_folder, str) and selected_folder.strip():
            selected_folder = os.path.abspath(os.path.normpath(selected_folder.strip()))
        self._state.selected_folder = selected_folder or None

    def set_processing(self, is_processing: bool, message: str = "") -> None:
        self._state.is_processing = bool(is_processing)
        self._state.processing_message = message if is_processing else ""

    def get_file(self, field: ForcingField) -> Optional[str]:
        return self._state.files.get(field)

    def set_file(self, field: ForcingField, path: Optional[str]) -> None:
        normalized = os.path.normpath(path) if isinstance(path, str) and path.strip() else None
        self._state.files.set(field, normalized)

    def clear_files(self, fields: Optional[Iterable[ForcingField]] = None) -> None:
        if fields is None:
            self._state.files.clear()
            return
        for field in fields:
            self._state.files.clear(field)

    def replace_files(self, files: Step1Files) -> None:
        self._state.files = files.copy()

    def update_files(self, files: Step1Files) -> None:
        for field in FORCING_FIELD_ORDER:
            path = files.get(field)
            if path:
                self.set_file(field, path)

    def reset_for_folder(self, selected_folder: Optional[str]) -> None:
        self.set_selected_folder(selected_folder)
        self.clear_files()
        self.set_processing(False)
