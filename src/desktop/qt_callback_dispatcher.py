"""Thread-safe delivery of workflow callbacks to Qt widgets."""

from __future__ import annotations

import threading
from collections.abc import Callable

from PyQt6 import QtCore

# Log lines are batched for this long before being handed to the widget.
# Short enough to still read as live output, long enough that a subprocess
# emitting thousands of lines costs a handful of updates instead of thousands.
_LOG_FLUSH_MS = 80

# Ceiling on the backlog.  The log widget keeps only its last few thousand
# blocks anyway, so dropping the oldest here loses nothing that would have
# survived, and it stops a runaway producer from growing this without bound.
_LOG_BACKLOG_LIMIT = 10_000

# Lines handed to the widget per tick.  Batching alone is not enough: a
# producer that fills the buffer before the first flush would otherwise turn
# into one enormous insert, which blocks the window just as effectively as the
# unbatched flood did.  A drained backlog simply takes a few more ticks.
_LOG_MAX_PER_FLUSH = 250


class QtCallbackDispatcher(QtCore.QObject):
    """Turn toolkit-agnostic workflow callbacks into queued Qt updates.

    Log lines are coalesced rather than delivered one signal at a time.  A
    background reader emits as fast as it can pull from a pipe, and Qt drains
    every posted event before it gets back to input and painting -- so an
    unbatched burst of a few thousand lines freezes the window for the better
    part of a second at a time.  Batching bounds the work done per pass no
    matter how fast the producer runs.
    """

    state_received = QtCore.pyqtSignal(object)
    _wake = QtCore.pyqtSignal()

    def __init__(
        self,
        *,
        on_log: Callable[[str], None],
        on_state_change: Callable[[object], None],
        parent: QtCore.QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._on_log = on_log
        self.state_received.connect(
            self._deliver_state, QtCore.Qt.ConnectionType.QueuedConnection
        )
        self._on_state_change = on_state_change

        self._buffer: list[str] = []
        self._dropped = 0
        self._running = False
        self._lock = threading.Lock()

        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(_LOG_FLUSH_MS)
        self._timer.timeout.connect(self._flush)
        # The timer lives in the thread that owns this object, so it can only
        # be started from there; posting through a queued signal gets us back
        # onto that thread from whichever one called post_log.
        self._wake.connect(self._ensure_running, QtCore.Qt.ConnectionType.QueuedConnection)

    # ── producer side (any thread) ────────────────────────────────────────
    def post_log(self, message: str) -> None:
        with self._lock:
            self._buffer.append(str(message))
            overflow = len(self._buffer) - _LOG_BACKLOG_LIMIT
            if overflow > 0:
                del self._buffer[:overflow]
                self._dropped += overflow
            # Only wake on the idle -> busy edge.  Posting one event per line
            # would put back the very flood this class exists to avoid.
            wake = not self._running
            self._running = True
        if wake:
            self._wake.emit()

    def post_state(self, state: object) -> None:
        self.state_received.emit(state)

    # ── consumer side (owning thread) ─────────────────────────────────────
    def _ensure_running(self) -> None:
        if not self._timer.isActive():
            self._timer.start()
            # Show the first lines immediately; waiting a tick before anything
            # appears reads as a stall of its own.
            self._flush()

    def _flush(self) -> None:
        with self._lock:
            if not self._buffer:
                self._timer.stop()
                self._running = False
                return
            batch = self._buffer[:_LOG_MAX_PER_FLUSH]
            del self._buffer[:_LOG_MAX_PER_FLUSH]
            dropped = self._dropped
            self._dropped = 0
        if dropped:
            batch.insert(0, f"… {dropped} 行日志因积压过多被丢弃 …")
        self._on_log("\n".join(batch))

    def _deliver_state(self, state: object) -> None:
        # Keep state changes behind the log lines that preceded them.
        self._flush()
        self._on_state_change(state)

    def flush_now(self) -> None:
        """Deliver anything buffered at once (call from the owning thread)."""
        self._flush()
