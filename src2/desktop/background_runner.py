"""Run workflow tasks off the UI thread and marshal results back to Qt."""

from __future__ import annotations

import threading
import traceback
import uuid
from typing import Callable

from PyQt6 import QtCore


class _BackgroundRunnerBridge(QtCore.QObject):
    finished = QtCore.pyqtSignal(str, object)


class BackgroundRunner:
    """Runs callables on daemon threads and delivers results on the UI thread."""

    def __init__(self, parent: QtCore.QObject | None = None) -> None:
        self._bridge = _BackgroundRunnerBridge(parent)
        self._bridge.finished.connect(self._dispatch, QtCore.Qt.ConnectionType.QueuedConnection)
        self._callbacks: dict[str, Callable[[object], None]] = {}

    def run(self, task: Callable[[], object], on_done: Callable[[object], None]) -> str:
        token = uuid.uuid4().hex
        self._callbacks[token] = on_done

        def _worker() -> None:
            try:
                result = task()
            except Exception as exc:
                traceback.print_exc()
                result = {"success": False, "error": str(exc)}
            self._bridge.finished.emit(token, result)

        threading.Thread(target=_worker, daemon=True).start()
        return token

    def _dispatch(self, token: str, result: object) -> None:
        callback = self._callbacks.pop(token, None)
        if callback is not None:
            try:
                callback(result)
            except Exception:
                traceback.print_exc()
