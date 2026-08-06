"""任务队列对话框：展示集群上所有用户的作业列表。

[EN] Job queue dialog: shows all users' jobs on the cluster.
复用集群监控页右侧列表的 OthersJobsTable —— 展示逻辑与集群监听页面完全一致。
"""

from __future__ import annotations

import platform

from PyQt6 import QtCore
from PyQt6.QtWidgets import QLabel, QSizePolicy, QVBoxLayout, QWidget
from qfluentwidgets import MessageBoxBase

from workflows.support.translations import tr

from ..windows.cluster_monitor import OthersJobsTable


class JobsQueueDialog(MessageBoxBase):
    """第六步"查看任务队列"弹窗：以集群监控页右侧列表同款表格展示所有任务。

    [EN] Step-6 "view job queue" dialog: shows all jobs in the same table style
    as the cluster monitor page right-side list.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("")
        if platform.system() == "Darwin":
            self.setStyleSheet("font-family: 'PingFang SC';")

        self.hideYesButton()
        self.hideCancelButton()
        self.buttonLayout.parent().setVisible(False)

        self._content_host = QWidget()
        self._content_host.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._content_layout = QVBoxLayout(self._content_host)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(6)
        self.viewLayout.addWidget(self._content_host, 1)

        self._summary = QLabel(tr("queue_dialog_summary", "任务队列"))
        self._content_layout.addWidget(self._summary)

        self._jobs_table = OthersJobsTable()
        self._content_layout.addWidget(self._jobs_table, 1)

        if hasattr(self, "setClosableOnMaskClicked"):
            self.setClosableOnMaskClicked(True)

        QtCore.QTimer.singleShot(0, self._fit_to_parent_window)

    def set_jobs(self, jobs: list, me: str) -> None:
        """填充任务数据（与集群监控页 update_others_jobs 同款逻辑）。"""
        jobs = jobs or []
        me = str(me or "")
        others = [j for j in jobs if str(j.get("user", "")) != me]
        mine = [j for j in jobs if str(j.get("user", "")) == me]
        self._summary.setText(
            tr(
                "queue_dialog_summary",
                "任务队列：共 {total} 个任务（本人 {mine} 个）",
            ).format(total=len(jobs), mine=len(mine))
        )
        self._jobs_table.update_others_jobs(jobs, me)

    def _fit_to_parent_window(self) -> None:
        parent = self.parentWidget()
        if parent is not None and parent.isVisible():
            w = int(parent.frameGeometry().width() * 0.72)
            h = int(parent.frameGeometry().height() * 0.72)
        else:
            w, h = 880, 560
        card = getattr(self, "widget", None)
        if card is not None:
            card.setFixedSize(max(w, 720), max(h, 420))
            card.updateGeometry()
        else:
            self.resize(max(w, 720), max(h, 420))
