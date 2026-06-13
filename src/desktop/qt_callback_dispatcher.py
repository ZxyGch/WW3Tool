"""Thread-safe delivery of workflow callbacks to Qt widgets."""

from __future__ import annotations

from collections.abc import Callable

from PyQt6 import QtCore


class QtCallbackDispatcher(QtCore.QObject):
    """Turn toolkit-agnostic workflow callbacks into queued Qt updates."""

    log_received = QtCore.pyqtSignal(str)
    state_received = QtCore.pyqtSignal(object)

    def __init__(
        self,
        *,
        on_log: Callable[[str], None],
        on_state_change: Callable[[object], None],
        parent: QtCore.QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.log_received.connect(on_log, QtCore.Qt.ConnectionType.QueuedConnection)
        self.state_received.connect(on_state_change, QtCore.Qt.ConnectionType.QueuedConnection)

    def post_log(self, message: str) -> None:
        self.log_received.emit(str(message))

    def post_state(self, state: object) -> None:
        self.state_received.emit(state)
