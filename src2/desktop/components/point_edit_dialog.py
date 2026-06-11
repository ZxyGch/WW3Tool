"""第三步单点录入/编辑对话框。

谱点输入 lon/lat/name；航迹点额外输入 datetime（``YYYYMMDD HHMMSS``）。
内部元素布局对齐 src step3：``MessageBoxBase`` + 标签/输入两列网格，输入框套用
窗口输入样式；点击确定时校验，不合法用 ``InfoBar`` 提示并阻止关闭。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from PyQt6.QtWidgets import QGridLayout, QLabel
from qfluentwidgets import InfoBar, LineEdit, MessageBoxBase
from .validators import datetime_yyyymmdd_hhmmss_validator, double_validator
from workflows.support.translations import tr

LON_RANGE = (-180.0, 180.0)
LAT_RANGE = (-90.0, 90.0)


class PointEditDialog(MessageBoxBase):
    """录入或编辑一个谱点 / 航迹点。

    参数:
        parent: 父窗口（应为顶层窗口，使遮罩覆盖整窗）。
        kind: ``"spectral"`` 或 ``"track"``。
        initial: 预填值（编辑时传入）。
        bounds: 可选网格包围盒，提供时额外校验是否落在网格范围内。
        input_style: 输入框样式表（与窗口其它输入框一致）。
        default_name: 名称留空时的默认值（新增时通常传当前序号）。

    成功后 ``self.value`` 为点位 dict：谱点 ``{"lon","lat","name"}``，
    航迹 ``{"datetime","lon","lat","name"}``。
    """

    def __init__(
        self,
        parent=None,
        *,
        kind: str = "spectral",
        initial: dict | None = None,
        bounds: dict | None = None,
        input_style: str = "",
        default_name: str = "",
    ) -> None:
        super().__init__(parent)
        self._kind = kind
        self._bounds = bounds
        self._default_name = default_name
        self.value: dict[str, Any] | None = None
        initial = initial or {}

        if getattr(self, "yesButton", None):
            self.yesButton.setText(tr("confirm", "确定"))
        if getattr(self, "cancelButton", None):
            self.cancelButton.setText(tr("cancel", "取消"))

        grid = QGridLayout()
        grid.setColumnStretch(0, 0)
        grid.setColumnStretch(1, 1)
        grid.setSpacing(10)
        row = 0

        self._datetime_edit: LineEdit | None = None
        if kind == "track":
            self._datetime_edit = self._add_field(
                grid,
                row,
                tr("step3_time", "时间:"),
                tr("step3_time_example", "例如: 20250101 000000"),
                str(initial.get("datetime", "")),
                input_style,
            )
            self._datetime_edit.setValidator(datetime_yyyymmdd_hhmmss_validator())
            row += 1
        self._lon_edit = self._add_field(
            grid, row, tr("step3_longitude_label", "经度:"), tr("step3_lon_example", "例如: 120.5"), _fmt(initial.get("lon")), input_style
        )
        self._lon_edit.setValidator(double_validator(LON_RANGE[0], LON_RANGE[1]))
        row += 1
        self._lat_edit = self._add_field(
            grid, row, tr("step3_latitude_label", "纬度:"), tr("step3_lat_example", "例如: 30.2"), _fmt(initial.get("lat")), input_style
        )
        self._lat_edit.setValidator(double_validator(LAT_RANGE[0], LAT_RANGE[1]))
        row += 1
        self._name_edit = self._add_field(
            grid, row, tr("step3_name_label", "名称:"), tr("step3_name_example", "例如: 点位1"), str(initial.get("name", "")), input_style
        )

        self.viewLayout.addLayout(grid)
        self.widget.setMinimumWidth(360)

    def _add_field(
        self, grid: QGridLayout, row: int, label: str, placeholder: str, value: str, input_style: str
    ) -> LineEdit:
        edit = LineEdit()
        edit.setPlaceholderText(placeholder)
        edit.setMinimumWidth(300)
        if input_style:
            edit.setStyleSheet(input_style)
        edit.setText(value)
        grid.addWidget(QLabel(label), row, 0)
        grid.addWidget(edit, row, 1)
        return edit

    def validate(self) -> bool:
        """qfluentwidgets 在点击确定时调用；返回 ``False`` 阻止关闭。"""
        try:
            lon = float(self._lon_edit.text().strip())
            lat = float(self._lat_edit.text().strip())
        except ValueError:
            return self._fail(tr("step3_lon_lat_must_be_number", "经度/纬度必须是数字"))
        if not (LON_RANGE[0] <= lon <= LON_RANGE[1]):
            return self._fail(tr("step3_lon_range_error", "经度必须在 -180 到 180 之间"))
        if not (LAT_RANGE[0] <= lat <= LAT_RANGE[1]):
            return self._fail(tr("step3_lat_range_error", "纬度必须在 -90 到 90 之间"))
        if self._bounds and not (
            self._bounds["lon_min"] <= lon <= self._bounds["lon_max"]
            and self._bounds["lat_min"] <= lat <= self._bounds["lat_max"]
        ):
            return self._fail(tr("step3_point_out_of_grid_range_short", "点位不在当前网格范围内"))

        name = self._name_edit.text().strip() or self._default_name
        result: dict[str, Any] = {"lon": lon, "lat": lat, "name": name or "Point"}
        if self._kind == "track":
            assert self._datetime_edit is not None
            dt = self._datetime_edit.text().strip()
            try:
                datetime.strptime(dt, "%Y%m%d %H%M%S")
            except ValueError:
                return self._fail(tr("step3_time_format_error", "时间须形如 YYYYMMDD HHMMSS，如 20250101 000000"))
            result = {"datetime": dt, **result}
            if not (name):
                result["name"] = "Track"
        self.value = result
        return True

    def _fail(self, message: str) -> bool:
        InfoBar.warning(title=tr("step3_add_failed", "添加失败"), content=message, duration=3000, parent=self)
        return False


def _fmt(value) -> str:
    if value is None or value == "":
        return ""
    try:
        return f"{float(value):g}"
    except (TypeError, ValueError):
        return str(value)
