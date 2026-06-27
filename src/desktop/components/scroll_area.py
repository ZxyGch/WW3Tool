"""Shared scroll area widgets."""

from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication, QScrollArea, QWidget


class NoHScrollArea(QScrollArea):
    """QScrollArea that completely disables horizontal scrolling."""

    def scrollContentsBy(self, dx: int, dy: int) -> None:  # noqa: N802
        super().scrollContentsBy(0, dy)

    def horizontalScrollBar(self):
        bar = super().horizontalScrollBar()
        bar.setRange(0, 0)
        return bar

    def preserve_vertical_scroll(self, fn: Callable[[], object]) -> None:
        """Run *fn* without letting child layout/focus changes move the viewport."""
        bar = self.verticalScrollBar()
        pos = bar.value()
        app = QApplication.instance()
        focus_before: QWidget | None = app.focusWidget() if app is not None else None

        fn()

        def restore() -> None:
            bar.setValue(pos)
            if focus_before is None:
                return
            current = app.focusWidget() if app is not None else None
            if current is not focus_before:
                try:
                    focus_before.setFocus()
                except RuntimeError:
                    pass

        restore()
        QTimer.singleShot(0, restore)

    def scroll_to_top(self) -> None:
        QTimer.singleShot(0, lambda: self.verticalScrollBar().setValue(0))
