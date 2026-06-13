"""无 Qt 依赖的控件存根，模拟 ``ModifyWW3NML`` / ``StepFourServiceMixin`` 期望的 Qt 接口。

这些类仅实现两个 Mixin 在运行时实际调用的 Qt 控件 API 子集，使 ``_WW3Adapter``
（``ww3_namelist_adapter.py``）可在不导入 Qt 的情况下继承上述 Mixin，遵循对象适配器模式：

- **桌面端路径**：真实 UI 控件 → Mixin 通过 ``self.widget.text()`` / ``.currentText()`` 读取值。
- **CLI 路径**：``_WW3Adapter`` 将 ``self.widget`` 设为 ``_TextValue(plain_value)``，
  Mixin 以相同 API 透明读取，无需分支判断。

[EN] Qt-free widget stubs that simulate the Qt interfaces expected by
``ModifyWW3NML`` / ``StepFourServiceMixin``.

These classes implement only the subset of Qt widget APIs actually invoked
by the two Mixins at runtime, allowing ``_WW3Adapter`` (``ww3_namelist_adapter.py``)
to inherit those Mixins without importing Qt, following the object adapter pattern:

- **Desktop path**: Real UI widgets -> Mixin reads values via
  ``self.widget.text()`` / ``.currentText()``.
- **CLI path**: ``_WW3Adapter`` sets ``self.widget`` to ``_TextValue(plain_value)``,
  and the Mixin reads transparently with the same API, no branching required.
"""

from __future__ import annotations

from typing import Any, List, Optional


class _TextValue:
    """``QLineEdit`` / ``QLabel`` 的字符串存根。

    [EN] String stub for ``QLineEdit`` / ``QLabel``.
    """

    def __init__(self, value: Any = "") -> None:
        """初始化文本值；``None`` 视为空字符串。

        [EN] Initialize the text value; ``None`` is treated as an empty string.
        """
        self._value = "" if value is None else str(value)

    def text(self) -> str:
        """返回当前存储的文本。

        [EN] Return the currently stored text.
        """
        return self._value

    def setText(self, value: Any) -> None:
        """设置文本内容；``None`` 视为空字符串。

        [EN] Set the text content; ``None`` is treated as an empty string.
        """
        self._value = "" if value is None else str(value)


class _ComboValue:
    """``QComboBox`` 的字符串存根；信号阻塞等操作为空实现。

    [EN] String stub for ``QComboBox``; signal blocking and similar operations
    are no-ops.
    """

    def __init__(self, value: Any = "") -> None:
        """初始化当前选中项文本。

        [EN] Initialize the currently selected item text.
        """
        self._value = "" if value is None else str(value)

    def currentText(self) -> str:
        """返回当前选中项文本（与 ``QComboBox.currentText`` 一致）。

        [EN] Return the currently selected item text
        (consistent with ``QComboBox.currentText``).
        """
        return self._value

    def setCurrentText(self, value: Any) -> None:
        """设置当前选中项文本。

        [EN] Set the currently selected item text.
        """
        self._value = "" if value is None else str(value)

    def blockSignals(self, _blocked: bool) -> None:
        """占位：CLI 存根无需阻塞 Qt 信号。

        [EN] Placeholder: CLI stub does not need to block Qt signals.
        """
        return None

    def clear(self) -> None:
        """清空下拉框内容（重置为空白）。

        [EN] Clear the dropdown contents (reset to blank).
        """
        self._value = ""

    def addItems(self, items: List[str]) -> None:
        """占位：CLI 存根不维护选项列表。

        [EN] Placeholder: CLI stub does not maintain an item list.
        """
        pass

    def setCurrentIndex(self, _index: int) -> None:
        """占位：CLI 存根不维护索引。

        [EN] Placeholder: CLI stub does not maintain an index.
        """
        pass

    def count(self) -> int:
        """返回选项数量（存根恒为 0）。

        [EN] Return the number of items (stub always returns 0).
        """
        return 0


class _Checkbox:
    """``QCheckBox`` 的布尔存根。

    [EN] Boolean stub for ``QCheckBox``.
    """

    def __init__(self, checked: bool) -> None:
        """初始化勾选状态。

        [EN] Initialize the checked state.
        """
        self._checked = bool(checked)

    def isChecked(self) -> bool:
        """返回是否勾选。

        [EN] Return whether the checkbox is checked.
        """
        return self._checked

    def setChecked(self, checked: bool) -> None:
        """设置勾选状态。

        [EN] Set the checked state.
        """
        self._checked = bool(checked)


class _Item:
    """``QTableWidgetItem`` 的单元格文本存根。

    [EN] Cell text stub for ``QTableWidgetItem``.
    """

    def __init__(self, value: Any) -> None:
        """初始化单元格显示文本。

        [EN] Initialize the cell display text.
        """
        self._value = "" if value is None else str(value)

    def text(self) -> str:
        """返回单元格文本。

        [EN] Return the cell text.
        """
        return self._value


class _Table:
    """``QTableWidget`` 的表格存根，以行列表为后端存储。

    [EN] Table stub for ``QTableWidget``, backed by a list of rows.
    """

    def __init__(self, rows: List[List[Any]]) -> None:
        """用二维列表初始化表格数据（行 × 列）。

        [EN] Initialize table data with a 2D list (rows x columns).
        """
        self._rows = rows

    def rowCount(self) -> int:
        """返回行数。

        [EN] Return the number of rows.
        """
        return len(self._rows)

    def item(self, row: int, column: int) -> Optional[_Item]:
        """返回指定行列的 ``_Item``；越界时返回 ``None``。

        [EN] Return the ``_Item`` at the specified row and column;
        returns ``None`` if out of bounds.
        """
        try:
            return _Item(self._rows[row][column])
        except IndexError:
            return None
