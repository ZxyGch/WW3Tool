"""Shared Fluent table whose visible row background reaches the widget edges."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QSizePolicy
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

    def expand_to_contents(self, *, minimum_height: int = 0, extra_height: int = 2) -> None:
        """Fix the table height to show every row without vertical scrolling."""
        self.resizeRowsToContents()
        rows_height = sum(self.rowHeight(row) for row in range(self.rowCount()))
        header_height = (
            self.horizontalHeader().height() if not self.horizontalHeader().isHidden() else 0
        )
        content_height = rows_height + header_height + 2 * self.frameWidth() + extra_height
        self.setFixedHeight(max(minimum_height, content_height))
