"""集群监控页：按钮样式一致性，以及两张任务表的高度分配。"""

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
    from PyQt6 import QtWidgets
    from qfluentwidgets import PrimaryPushButton
    from desktop.components.table_widget import EdgeAlignedTableWidget
    from desktop.windows import cluster_monitor as cm
except ImportError as exc:  # pragma: no cover - PyQt6 not installed
    raise unittest.SkipTest(f"PyQt6 不可用：{exc}")

_app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _job(user, jid):
    return {"user": user, "jobid": str(jid), "name": f"j{jid}", "state": "RUNNING",
            "partition": "P", "elapsed": "1:00:00", "cpus": "16",
            "nodes": "1", "nodelist": "n1"}


class LaidOutHeightTest(unittest.TestCase):
    """setFixedHeight 不改变 sizeHint，所以量高度必须看约束而不是建议值。"""

    def test_fixed_height_wins_over_the_hint(self):
        for rows in (1, 3, 12):
            t = EdgeAlignedTableWidget()
            t.setColumnCount(4)
            t.setRowCount(rows)
            for r in range(rows):
                for c in range(4):
                    t.setItem(r, c, QtWidgets.QTableWidgetItem("x"))
            t.horizontalHeader().setVisible(False)
            t.show()
            t.expand_to_contents(extra_height=6, max_row_height=32)
            self.assertEqual(cm._laid_out_height(t), t.maximumHeight())

    def test_table_hint_really_is_content_independent(self):
        # 这条记录的是「为什么不能用 sizeHint」：行数变了，hint 不变。
        hints = []
        for rows in (1, 12):
            t = EdgeAlignedTableWidget()
            t.setColumnCount(4)
            t.setRowCount(rows)
            t.show()
            hints.append(t.sizeHint().height())
        self.assertEqual(hints[0], hints[1])

    def test_hidden_widget_takes_no_room(self):
        t = EdgeAlignedTableWidget()
        self.assertEqual(cm._laid_out_height(t), 0)

    def test_unconstrained_widget_falls_back_to_the_hint(self):
        w = QtWidgets.QLabel("x")
        w.show()
        self.assertEqual(cm._laid_out_height(w), w.sizeHint().height())


class TaskActionButtonStyleTest(unittest.TestCase):
    """两个按钮要和同卡片其余按钮走同一套样式。"""

    def test_action_buttons_are_primary_push_buttons(self):
        # _refresh_manual_styles 只对 PrimaryPushButton 套用 styles.button_style()。
        src = (REPO_ROOT / "src" / "desktop" / "windows" / "cluster_monitor.py").read_text(
            encoding="utf-8")
        self.assertIn('self.watch_button = PrimaryPushButton(', src)
        self.assertIn('self.cancel_button = PrimaryPushButton(', src)

    def test_no_plain_push_button_is_left_in_the_window(self):
        src = (REPO_ROOT / "src" / "desktop" / "windows" / "cluster_monitor.py").read_text(
            encoding="utf-8")
        self.assertNotIn(" PushButton(", src.replace("PrimaryPushButton(", ""))


class JobTableHeightAllocationTest(unittest.TestCase):
    """两张任务表都按内容完整展开，放不下时由右侧滚动区整体滚动。"""

    def _panel(self, n_mine, n_others, card_h=700):
        win = QtWidgets.QWidget()
        win.resize(900, card_h)
        lay = QtWidgets.QVBoxLayout(win)
        lay.setContentsMargins(0, 0, 0, 0)
        panel = cm.OthersJobsTable(win)
        lay.addWidget(panel)
        win.show()
        panel.update_others_jobs(
            [_job("me", i) for i in range(n_mine)]
            + [_job(f"u{i}", 1000 + i) for i in range(n_others)], "me")
        for _ in range(30):
            _app.processEvents()
        self._win = win          # 保持引用，避免被回收
        return panel

    def _resize(self, panel, height):
        panel.window().resize(900, height)
        for _ in range(40):
            _app.processEvents()

    def test_others_always_shows_every_row(self):
        # 表内滚动会把"还有多少任务"藏起来，而这正是这个页面要回答的问题
        for n_others in (3, 10, 40, 80):
            panel = self._panel(3, n_others)
            ot = panel._others_table
            self.assertEqual(ot.height(), int(ot.property("_content_h") or 0),
                             msg=f"他人任务 {n_others} 条时没有完整展开")

    def test_neither_table_scrolls_internally(self):
        panel = self._panel(25, 80)
        for name, table in (("others", panel._others_table), ("mine", panel._mine_table)):
            self.assertFalse(table.verticalScrollBar().isVisible(),
                             msg=f"{name} 出现了表内滚动条")

    def test_my_jobs_is_never_truncated(self):
        for n_mine in (1, 3, 8, 12, 30):
            panel = self._panel(n_mine, 40)
            mt = panel._mine_table
            self.assertGreaterEqual(mt.height(), (n_mine + 1) * 32,
                                    msg=f"My Jobs {n_mine} 行被压缩了")

    def test_window_height_does_not_change_the_tables(self):
        # 完全展开后高度只由内容决定；曾经它跟着窗口走，且 resize 时不重算，
        # 多出来的空间被卡片底部的弹簧吸走 —— others 挤在上面滚动、My Jobs
        # 下面一大片空白，正是用户报的现象
        panel = self._panel(3, 40, card_h=420)
        heights = []
        for height in (420, 900, 620, 1200, 380):
            self._resize(panel, height)
            heights.append((panel._others_table.height(), panel._mine_table.height()))
        self.assertEqual(len(set(heights)), 1, msg=f"高度随窗口变了：{heights}")

    def test_content_taller_than_the_pane_stays_reachable(self):
        # 完整展开意味着内容会超出视口，必须能滚到底，否则等于被裁掉
        win = cm.ClusterMonitorInterface()
        win.resize(1400, 800)
        win.show()
        for _ in range(40):
            _app.processEvents()
        win._others_jobs_panel.update_others_jobs(
            [_job("me", i) for i in range(3)]
            + [_job(f"u{i}", 1000 + i) for i in range(60)], "me")
        for _ in range(60):
            _app.processEvents()
        self._win = win
        w = win._others_jobs_panel.parentWidget()
        while w is not None and not isinstance(w, QtWidgets.QScrollArea):
            w = w.parentWidget()
        self.assertIsNotNone(w, "面板不在滚动区里，超出的内容将无法到达")
        overflow = w.widget().height() - w.viewport().height()
        self.assertGreater(overflow, 0, "内容没有超出视口，这条用例失去意义")
        self.assertGreaterEqual(w.verticalScrollBar().maximum(), overflow - 8,
                                "滚动范围盖不住超出的内容")

    def test_short_lists_do_not_scroll(self):
        panel = self._panel(2, 3)
        ot = panel._others_table
        self.assertLessEqual(int(ot.property("_content_h") or 0), ot.height())


if __name__ == "__main__":
    unittest.main()
