"""Shared Fluent table whose visible row background reaches the widget edges."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QHeaderView, QSizePolicy
from qfluentwidgets import TableWidget
from qfluentwidgets.components.widgets.table_view import TableItemDelegate


class _EdgeAlignedTableItemDelegate(TableItemDelegate):
    """Remove Fluent's four-pixel outer row inset while keeping its styling."""

    def _drawBackground(self, painter, option, index) -> None:
        radius = 5
        last_column = index.model().columnCount(index.parent()) - 1
        if index.column() == 0:
            painter.drawRoundedRect(option.rect.adjusted(0, 0, radius + 1, 0), radius, radius)
        elif index.column() == last_column:
            painter.drawRoundedRect(option.rect.adjusted(-radius - 1, 0, 0, 0), radius, radius)
        else:
            painter.drawRect(option.rect.adjusted(-1, 0, 1, 0))


class EdgeAlignedTableWidget(TableWidget):
    """Fluent table with visible rows aligned to surrounding controls."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setItemDelegate(_EdgeAlignedTableItemDelegate(self))
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def expand_to_contents(
        self,
        *,
        minimum_height: int = 0,
        extra_height: int = 2,
        max_row_height: int | None = None,
    ) -> None:
        """Fix the table height to show every row without vertical scrolling.

        max_row_height: 若给定，把行高压缩到该上限（默认 qfluentwidgets 行高 ~39px，
        对 14px 字号偏大；传 32 可让列表更紧凑）。
        """
        self.resizeRowsToContents()
        if max_row_height:
            # ResizeToContents 模式会覆盖 setRowHeight，先切到 Fixed 再压缩行高
            self.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
            for row in range(self.rowCount()):
                if self.rowHeight(row) > max_row_height:
                    self.setRowHeight(row, max_row_height)
        rows_height = sum(self.rowHeight(row) for row in range(self.rowCount()))
        header_height = (
            self.horizontalHeader().height() if not self.horizontalHeader().isHidden() else 0
        )
        content_height = rows_height + header_height + 2 * self.frameWidth() + extra_height
        self.setFixedHeight(max(minimum_height, content_height))
