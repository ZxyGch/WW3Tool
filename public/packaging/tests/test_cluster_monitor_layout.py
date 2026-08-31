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
    """My Jobs 优先完整显示，剩余高度归 others。"""

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

    @staticmethod
    def _slack(panel):
        inner = panel._card.viewLayout.itemAt(0).layout()
        used = (panel._others_table.height()
                + cm._laid_out_height(panel._my_jobs_title)
                + cm._laid_out_height(panel._mine_table)
                + inner.spacing() * 3)
        return inner.geometry().height() - used

    def test_no_empty_space_while_others_scrolls(self):
        # 这是用户报的问题：下方空着，others 却在滚动。
        for n_mine in (1, 2, 3, 5, 8):
            panel = self._panel(n_mine, 40)
            ot = panel._others_table
            scrolling = int(ot.property("_content_h") or 0) > ot.height()
            self.assertTrue(scrolling, msg=f"{n_mine} 行时 others 应当仍需滚动")
            self.assertLessEqual(abs(self._slack(panel)), 8,
                                 msg=f"My Jobs {n_mine} 行时下方不应有空隙")

    def test_my_jobs_is_never_truncated(self):
        for n_mine in (1, 3, 8, 12):
            panel = self._panel(n_mine, 40)
            mt = panel._mine_table
            self.assertGreaterEqual(mt.height(), (n_mine + 1) * 32,
                                    msg=f"My Jobs {n_mine} 行被压缩了")

    def test_others_shrinks_as_my_jobs_grows(self):
        heights = [self._panel(n, 40)._others_table.height() for n in (1, 3, 8)]
        self.assertGreater(heights[0], heights[1])
        self.assertGreater(heights[1], heights[2])

    def _resize(self, panel, height):
        panel.window().resize(900, height)
        for _ in range(40):
            _app.processEvents()

    def test_resizing_the_window_refits_the_others_table(self):
        # 用户报的问题：窗口变大后 others 仍停在旧高度，多出来的空间被卡片
        # 底部的弹簧吸走，看起来就是 others 挤在上面滚动、My Jobs 下面一大片空白
        panel = self._panel(3, 40, card_h=420)
        before = panel._others_table.height()
        self._resize(panel, 900)
        self.assertGreater(panel._others_table.height(), before + 200,
                           msg="窗口变大后 others 没有跟着变高")
        self.assertLessEqual(abs(self._slack(panel)), 8, msg="窗口变大后下方留白了")

    def test_shrinking_the_window_refits_too(self):
        # setFixedHeight 会一并抬高 minimumHeight；若它累加成面板的最小高度，
        # 窗口会被 Qt 提前钳住，缩小方向就再也收不回来
        panel = self._panel(3, 40, card_h=900)
        tall = panel._others_table.height()
        self._resize(panel, 420)
        self.assertLess(panel._others_table.height(), tall - 200,
                        msg="窗口缩小后 others 没有跟着变矮")
        self.assertLessEqual(abs(self._slack(panel)), 8, msg="窗口缩小后布局没收拢")

    def test_repeated_resizes_are_stable_and_converge(self):
        panel = self._panel(3, 40, card_h=700)
        seen = {}
        for height in (900, 620, 900, 620, 900):
            self._resize(panel, height)
            seen.setdefault(height, []).append(panel._others_table.height())
        for height, values in seen.items():
            self.assertEqual(len(set(values)), 1,
                             msg=f"窗口高 {height} 反复出现时结果不一致：{values}")

    def test_panel_can_shrink_no_matter_how_long_the_lists_are(self):
        # 面板的最小高度必须是常量：表格的 setFixedHeight 会一并抬高
        # minimumHeight，累加上去就会把窗口顶住，缩小时 Qt 先钳死尺寸，
        # 等重算跑起来时量到的已经是旧的大高度
        panel = self._panel(20, 60, card_h=900)
        self._resize(panel, 380)
        self.assertLessEqual(panel.height(), 400,
                             msg=f"内容一多面板就缩不回去了：{panel.height()}")

    def test_my_jobs_never_overflows_the_card(self):
        # 右侧滚动区关掉了竖直滚动条，溢出卡片的行在界面上够不着
        for n_mine in (15, 25, 40):
            panel = self._panel(n_mine, 40, card_h=700)
            inner = panel._card.viewLayout.itemAt(0).layout()
            used = (panel._others_table.height()
                    + cm._laid_out_height(panel._my_jobs_title)
                    + cm._laid_out_height(panel._mine_table)
                    + inner.spacing() * 3)
            self.assertLessEqual(used, inner.geometry().height() + 8,
                                 msg=f"我的任务 {n_mine} 行时内容溢出了卡片")

    def test_short_lists_do_not_scroll(self):
        panel = self._panel(2, 3)
        ot = panel._others_table
        self.assertLessEqual(int(ot.property("_content_h") or 0), ot.height())


if __name__ == "__main__":
    unittest.main()
