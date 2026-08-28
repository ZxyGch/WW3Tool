"""强迫场变量映射/服务器路径对话框（方案 §9 + 服务器路径扩展）。

[EN] Forcing variable mapping / server-path dialog (spec §9 + server-path extension).

样式对齐「创建工作目录」弹窗：``qfluentwidgets.MessageBoxBase``（非系统样式）。
内容：
1. 强迫场文件路径（服务器）输入框 —— 填写后本机不再导入/处理该场，
   服务器端直接使用此路径；
2. 按角色显示的下拉框（如风场：经度、纬度、时间、U、V），留空表示自动识别；
3. 确认时校验：路径与变量映射至少填一项。

[EN] Styling matches the "create work directory" dialog:
``qfluentwidgets.MessageBoxBase`` (not the native style). Contents:
1. Forcing file path (server) input — when filled, the field is NOT imported
   or processed locally; the server uses this path directly;
2. Role-based dropdowns (e.g. wind: longitude, latitude, time, U, V); empty
   means auto-detection;
3. Validation on confirm: at least one of path / variable mapping must be set.
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional

from PyQt6.QtWidgets import QFileDialog, QGridLayout, QHBoxLayout, QLabel, QWidget
from qfluentwidgets import InfoBar, LineEdit, MessageBoxBase, PrimaryPushButton

from workflows.support.translations import tr
from workflows.infrastructure.forcing.forcing_variable_resolver import VariableInfo

# 角色显示顺序与必填性（thickness 可选；服务器路径场景允许全部留空自动识别）
# [EN] Role display order (thickness optional; all may be left empty for
# auto-detection in the server-path scenario)
_FIELD_ROLES: Dict[str, List[str]] = {
    "wind": ["longitude", "latitude", "time", "u", "v"],
    "current": ["longitude", "latitude", "time", "u", "v"],
    "level": ["longitude", "latitude", "time", "value"],
    "ice": ["longitude", "latitude", "time", "concentration", "thickness"],
}

# 角色标签：tr key → 中文默认值（语言文件覆盖英文）
# [EN] Role labels: tr key → Chinese default (language files provide English)
_ROLE_LABEL_KEYS: Dict[str, str] = {
    "longitude": "forcing_role_longitude",
    "latitude": "forcing_role_latitude",
    "time": "forcing_role_time",
    "u": "forcing_role_u",
    "v": "forcing_role_v",
    "value": "forcing_role_value",
    "concentration": "forcing_role_concentration",
    "thickness": "forcing_role_thickness",
}

_ROLE_LABEL_DEFAULTS: Dict[str, str] = {
    "longitude": "经度",
    "latitude": "纬度",
    "time": "时间",
    "u": "U 分量",
    "v": "V 分量",
    "value": "水位值",
    "concentration": "海冰浓度",
    "thickness": "海冰厚度（可选）",
}

_FIELD_NAME_DEFAULTS = {
    "wind": "风场",
    "current": "流场",
    "level": "水位场",
    "ice": "海冰场",
}


def _role_label(role: str) -> str:
    """按当前语言返回角色标签（中文默认值，语言文件覆盖英文）。

    [EN] Return the role label in the current language (Chinese default;
    language files provide English).
    """
    key = _ROLE_LABEL_KEYS.get(role, role)
    return tr(key, _ROLE_LABEL_DEFAULTS.get(role, role))


def _auto_text() -> str:
    """按当前语言返回「自动识别」占位文本。

    [EN] Return the "auto-detect" placeholder text in the current language.
    """
    return tr("forcing_mapping_auto_text", "（自动识别）")


class ForcingVariableMappingDialog(MessageBoxBase):
    """变量映射 + 服务器路径编辑窗口（qfluentwidgets 样式）。

    [EN] Variable mapping + server-path edit dialog (qfluentwidgets style).

    成功后：
    - ``self.remote_path``：服务器强迫场路径（可为空）
    - ``self.mapping``：角色 → 变量名（None 表示自动识别）
    """

    def __init__(
        self,
        parent: Optional[QWidget],
        field: str,
        file_path: str,
        variables: Dict[str, VariableInfo],
        current: Optional[dict],
        remote_path: str = "",
        input_style: Callable[[], str] = lambda: "",
    ) -> None:
        super().__init__(parent)
        self._field = field
        self._roles = _FIELD_ROLES.get(field, [])
        self._combos: Dict[str, LineEdit] = {}
        self._current = current or {}
        self.remote_path: str = ""
        self.mapping: dict = {}
        title = QLabel(
            tr("forcing_mapping_title", "变量映射：{field}").format(
                field=tr(f"step2_field_{field}", _FIELD_NAME_DEFAULTS.get(field, field))
            )
        )
        title.setStyleSheet("font-size: 16px; font-weight: 600;")
        self.viewLayout.addWidget(title)
        self._input_style = input_style
        self._build_body(file_path, remote_path, variables)
        self.yesButton.setText(tr("confirm", "确定"))
        self.cancelButton.setText(tr("cancel", "取消"))

    def _build_body(self, file_path: str, remote_path: str, variables: Dict[str, VariableInfo]) -> None:
        grid = QGridLayout()
        grid.setSpacing(8)

        # 文件路径（服务器）：填写后本机不处理，服务器端直接使用
        # [EN] Server file path: when filled, the field is not processed locally
        row = 0
        grid.addWidget(QLabel(tr("forcing_mapping_server_path", "强迫场文件路径（服务器）：")), row, 0)
        path_row = QHBoxLayout()
        self.path_edit = LineEdit()
        self.path_edit.setText(remote_path)
        self.path_edit.setPlaceholderText(
            tr("forcing_mapping_server_path_placeholder", "如 /data/forcing/wind.nc（留空则使用本机文件）")
        )
        self.path_edit.setStyleSheet(self._input_style())
        path_row.addWidget(self.path_edit, 1)
        browse = PrimaryPushButton(tr("browse", "浏览"))
        browse.clicked.connect(self._browse_path)
        path_row.addWidget(browse)
        grid.addLayout(path_row, row, 1)
        self.viewLayout.addLayout(grid)

        self.viewLayout.addWidget(
            QLabel(
                tr(
                    "forcing_mapping_hint",
                    "为 {field} 选择每个角色对应的变量；留空（自动识别）时按常见名称与 CF 属性判断。",
                ).format(field=self._field)
            )
        )

        roles_grid = QGridLayout()
        roles_grid.setSpacing(8)
        candidates_hint = "\n".join(info.summary() for info in sorted(variables.values(), key=lambda v: v.name))
        for idx, role in enumerate(self._roles):
            roles_grid.addWidget(QLabel(_role_label(role) + "："), idx, 0)
            combo = LineEdit()
            combo.setPlaceholderText(_auto_text())
            combo.setStyleSheet(self._input_style())
            if candidates_hint:
                combo.setToolTip(tr("forcing_mapping_candidates", "可用变量：\n{vars}").format(vars=candidates_hint))
            saved = self._current.get(role)
            if saved and saved in variables:
                combo.setText(saved)
            self._combos[role] = combo
            roles_grid.addWidget(combo, idx, 1)
        self.viewLayout.addLayout(roles_grid)

        if file_path:
            self.viewLayout.addWidget(
                QLabel(tr("forcing_mapping_file", "本机文件：{path}").format(path=file_path))
            )

    def _browse_path(self) -> None:
        # 这里填的是**服务器**上的路径，不能按本地路径规范化：在 Windows 上
        # normalize_local_path 会把 /data/wind.nc 变成 \data\wind.nc。
        # [EN] This field holds a path on the *server*, so it must not go
        # through normalize_local_path: on Windows that would turn
        # /data/wind.nc into \data\wind.nc.
        selected, _ = QFileDialog.getOpenFileName(
            self,
            tr("choose_forcing_file", "选择强迫场文件"),
            "",
            tr("file_filter_netcdf_all", "NetCDF 文件 (*.nc *.nc4 *.cdf);;所有文件 (*)"),
        )
        if selected:
            self.path_edit.setText(selected)

    def validate(self) -> bool:
        """确认校验：路径与变量映射至少填一项。

        [EN] Confirm validation: at least one of path / variable mapping set.
        """
        path = self.path_edit.text().strip()
        mapping = {role: (edit.text().strip() or None) for role, edit in self._combos.items()}
        if not path and not any(mapping.values()):
            InfoBar.warning(
                title=tr("tip", "提示"),
                content=tr(
                    "forcing_mapping_empty",
                    "请至少填写服务器文件路径或一个变量映射；全部留空将使用自动识别（需本机文件）。",
                ),
                duration=3000,
                parent=self,
            )
            return False
        self.remote_path = path
        self.mapping = mapping
        return True
