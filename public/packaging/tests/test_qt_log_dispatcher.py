"""日志分发器必须把突发合并成有限的几次更新。

[EN] A background reader emits as fast as it can pull from a pipe.  Qt drains
every posted event before returning to input and painting, so one signal per
line freezes the window; and one giant insert is no better.  The dispatcher
has to bound both the number of updates and the size of each one.
"""

import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO_ROOT = Path(__file__).resolve().parents[3]
SRC = str(REPO_ROOT / "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

try:
    from PyQt6 import QtCore, QtWidgets
    from desktop.qt_callback_dispatcher import (
        _LOG_BACKLOG_LIMIT,
        _LOG_MAX_PER_FLUSH,
        QtCallbackDispatcher,
    )
except ImportError as exc:  # pragma: no cover - PyQt6 not installed
    raise unittest.SkipTest(f"PyQt6 不可用：{exc}")


_app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


class DispatcherTest(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.states = []
        self.d = QtCallbackDispatcher(
            on_log=self.calls.append,
            on_state_change=self.states.append,
        )

    def _drain(self, rounds=400):
        for _ in range(rounds):
            _app.processEvents()

    def test_a_burst_becomes_few_updates(self):
        n = 1000
        for i in range(n):
            self.d.post_log(f"line {i}")
        self.d.flush_now()
        self._drain()
        # 关键：更新次数远少于行数，否则就是原来的每行一个事件。
        self.assertLess(len(self.calls), n / 10)
        self.assertGreater(len(self.calls), 0)

    def test_every_line_survives_in_order(self):
        for i in range(600):
            self.d.post_log(f"line {i}")
        for _ in range(50):
            self.d.flush_now()
        lines = "\n".join(self.calls).split("\n")
        self.assertEqual(lines, [f"line {i}" for i in range(600)])

    def test_no_single_update_is_oversized(self):
        for i in range(2000):
            self.d.post_log(f"line {i}")
        for _ in range(50):
            self.d.flush_now()
        for chunk in self.calls:
            self.assertLessEqual(len(chunk.split("\n")), _LOG_MAX_PER_FLUSH)

    def test_backlog_is_capped_and_the_loss_is_reported(self):
        for i in range(_LOG_BACKLOG_LIMIT + 500):
            self.d.post_log(f"line {i}")
        self.d.flush_now()
        self.assertTrue(self.calls)
        self.assertIn("丢弃", self.calls[0])

    def test_nothing_is_delivered_before_it_is_posted(self):
        self.assertEqual(self.calls, [])

    def test_empty_flush_is_harmless(self):
        self.d.flush_now()
        self.d.flush_now()
        self.assertEqual(self.calls, [])

    def test_state_arrives_after_the_logs_that_preceded_it(self):
        self.d.post_log("before state")
        self.d.post_state({"tag": "s"})
        self._drain()
        self.assertTrue(self.calls, "状态到达时日志应已刷出")
        self.assertIn("before state", "\n".join(self.calls))
        self.assertEqual(len(self.states), 1)


if __name__ == "__main__":
    unittest.main()
