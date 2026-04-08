"""
Step 1 state models and forcing field helpers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ForcingField(str, Enum):
    WIND = "wind"
    CURRENT = "current"
    LEVEL = "level"
    ICE = "ice"


FORCING_FIELD_ORDER = (
    ForcingField.WIND,
    ForcingField.CURRENT,
    ForcingField.LEVEL,
    ForcingField.ICE,
)


LEGACY_FILE_ATTRS = {
    ForcingField.WIND: "selected_origin_file",
    ForcingField.CURRENT: "selected_current_file",
    ForcingField.LEVEL: "selected_level_file",
    ForcingField.ICE: "selected_ice_file",
}


@dataclass
class Step1Files:
    wind: Optional[str] = None
    current: Optional[str] = None
    level: Optional[str] = None
    ice: Optional[str] = None

    def get(self, field: ForcingField) -> Optional[str]:
        return getattr(self, field.value)

    def set(self, field: ForcingField, path: Optional[str]) -> None:
        setattr(self, field.value, path)

    def clear(self, field: Optional[ForcingField] = None) -> None:
        if field is None:
            for forcing_field in FORCING_FIELD_ORDER:
                self.set(forcing_field, None)
            return
        self.set(field, None)

    def copy(self) -> "Step1Files":
        return Step1Files(
            wind=self.wind,
            current=self.current,
            level=self.level,
            ice=self.ice,
        )

    def existing_items(self) -> list[tuple[ForcingField, str]]:
        items: list[tuple[ForcingField, str]] = []
        for field in FORCING_FIELD_ORDER:
            path = self.get(field)
            if path:
                items.append((field, path))
        return items


ForcingSelection = Step1Files


@dataclass
class Step1State:
    selected_folder: Optional[str] = None
    files: Step1Files = field(default_factory=Step1Files)
    is_processing: bool = False
    processing_message: str = ""
    auto_associate: bool = True
    process_mode: str = "copy"

    def copy(self) -> "Step1State":
        return Step1State(
            selected_folder=self.selected_folder,
            files=self.files.copy(),
            is_processing=self.is_processing,
            processing_message=self.processing_message,
            auto_associate=self.auto_associate,
            process_mode=self.process_mode,
        )
