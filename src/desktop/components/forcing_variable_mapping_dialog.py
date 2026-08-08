"""强迫场变量映射对话框（方案 §9）。

[EN] Forcing variable mapping dialog (spec §9).

按角色显示下拉框（如风场显示经度、纬度、时间、U、V），下拉项显示变量名、
维度与单位；必需项未完成时禁止确认；确认后把映射写入工作目录
``params.yml`` 的 ``forcing.custom``。

[EN] Shows one dropdown per role (e.g. wind: longitude, latitude, time, U, V);
each dropdown entry shows variable name, dimensions, and units. Confirmation is
disabled until all required roles are filled; on confirm the mapping is written
to ``forcing.custom`` in the workdir ``params.yml``.
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from workflows.support.translations import tr
from workflows.infrastructure.forcing.forcing_variable_resolver import VariableInfo

# 角色显示顺序与必填性（thickness 可选）
# [EN] Role display order and requiredness (thickness optional)
_FIELD_ROLES: Dict[str, List[str]] = {
    "wind": ["longitude", "latitude", "time", "u", "v"],
    "current": ["longitude", "latitude", "time", "u", "v"],
    "level": ["longitude", "latitude", "time", "value"],
    "ice": ["longitude", "latitude", "time", "concentration", "thickness"],
}

_ROLE_LABELS: Dict[str, str] = {
    "longitude": "经度 Longitude",
    "latitude": "纬度 Latitude",
    "time": "时间 Time",
    "u": "U 分量",
    "v": "V 分量",
    "value": "水位值 Value",
    "concentration": "海冰浓度 Concentration",
    "thickness": "海冰厚度 Thickness（可选）",
}

_AUTO_TEXT = "（自动识别 / auto-detect）"


class ForcingVariableMappingDialog(QDialog):
    """按角色选择强迫场变量的映射窗口。

    [EN] Role-based forcing variable mapping dialog.
    """

    def __init__(
        self,
        parent: Optional[QWidget],
        field: str,
        file_path: str,
        variables: Dict[str, VariableInfo],
        current: Optional[dict],
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(
            tr("forcing_mapping_title", "变量映射：{field}").format(
                field={"wind": "风场", "current": "流场", "level": "水位场", "ice": "海冰场"}.get(field, field)
            )
        )
        self.setMinimumWidth(520)
        self._field = field
        self._roles = _FIELD_ROLES.get(field, [])
        self._combos: Dict[str, QComboBox] = {}
        self._current = current or {}

        layout = QVBoxLayout(self)
        hint = QLabel(
            tr(
                "forcing_mapping_hint",
                "为 {field} 选择每个角色对应的变量。留空（自动识别）时将按常见名称与 CF 属性自动判断。",
            ).format(field=field)
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)
        layout.addWidget(QLabel(tr("forcing_mapping_file", "文件：{path}").format(path=file_path)))

        grid = QGridLayout()
        grid.setSpacing(8)
        for row, role in enumerate(self._roles):
            grid.addWidget(QLabel(_ROLE_LABELS.get(role, role) + "："), row, 0)
            combo = QComboBox()
            combo.addItem(_AUTO_TEXT, None)
            for name in sorted(variables):
                combo.addItem(variables[name].summary(), name)
            saved = self._current.get(role)
            if saved and saved in variables:
                combo.setCurrentText(variables[saved].summary())
            self._combos[role] = combo
            grid.addWidget(combo, row, 1)
        layout.addLayout(grid)

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._buttons.accepted.connect(self._on_accept)
        self._buttons.rejected.connect(self.reject)
        layout.addWidget(self._buttons)

    def _on_accept(self) -> None:
        missing = [
            role
            for role in self._roles
            if role != "thickness" and self._combos[role].currentData() is None
        ]
        if missing:
            from PyQt6.QtWidgets import QMessageBox

            QMessageBox.warning(
                self,
                tr("forcing_mapping_incomplete", "映射不完整"),
                tr(
                    "forcing_mapping_required_missing",
                    "以下必需角色尚未指定：{roles}",
                ).format(roles=", ".join(_ROLE_LABELS.get(r, r) for r in missing)),
            )
            return
        self.accept()

    def mapping(self) -> dict:
        """返回角色 → 变量名（或 None 表示自动识别）的字典。

        [EN] Return role → variable name (or None for auto-detect).
        """
        return {role: self._combos[role].currentData() for role in self._roles}
