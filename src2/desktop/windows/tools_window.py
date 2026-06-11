"""工具子界面：清理工作目录（迁移自 src ``_create_tools_page``）。

作为 FluentWindow 左侧堆叠的一页，右侧共享日志常驻。删除逻辑为纯函数（无 Qt），
界面按钮经构造注入的回调交由窗口执行（确认对话框 + 日志）。
"""

from __future__ import annotations

import os
from collections.abc import Callable

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QScrollArea, QSizePolicy, QVBoxLayout, QWidget
from qfluentwidgets import PrimaryPushButton

from ..components.header_card import create_header_card
from ..components import styles
from workflows.support.translations import tr


class _NoHScrollArea(QScrollArea):
    """QScrollArea that completely disables horizontal scrolling."""

    def scrollContentsBy(self, dx: int, dy: int) -> None:  # noqa: N802
        super().scrollContentsBy(0, dy)

    def horizontalScrollBar(self):
        bar = super().horizontalScrollBar()
        bar.setRange(0, 0)
        return bar


class ToolsInterface(QWidget):
    """常用工具页：清理工作目录。"""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        clean_all: Callable[[], None],
        clean_run: Callable[[], None],
    ) -> None:
        super().__init__(parent)
        self.setObjectName("tools_interface")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = _NoHScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        content = QWidget()
        content.setStyleSheet("QWidget { background: transparent; }")
        vbox = QVBoxLayout(content)
        vbox.setContentsMargins(0, 0, 0, 10)
        vbox.setSpacing(14)
        scroll.setWidget(content)
        outer.addWidget(scroll)

        group, layout = create_header_card(content, tr("tools_clean_workdir_card_title", "清理工作目录"))
        layout.addWidget(self._button(tr("tools_clean_workdir_all", "清空所有文件"), clean_all))
        layout.addWidget(self._button(tr("tools_clean_workdir_run_files", "清空运行文件 (.ww3 .log .bin)"), clean_run))
        group.viewLayout.setContentsMargins(11, 10, 11, 12)
        group.viewLayout.addLayout(layout)
        vbox.addWidget(group)
        vbox.addStretch(1)

    @staticmethod
    def _button(text: str, handler: Callable[[], None]) -> PrimaryPushButton:
        button = PrimaryPushButton(text)
        button.setStyleSheet(styles.button_style())
        button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        button.clicked.connect(handler)
        return button


# ── 删除逻辑（纯函数，无 Qt）────────────────────────────────────────────────


def should_remove_run_artifact(filename: str) -> bool:
    """运行产物：``.log`` / ``.bin`` / ``.ww3``（保留 grid.ww3）。"""
    lower = filename.lower()
    if lower.endswith(".log") or lower.endswith(".bin"):
        return True
    if lower.endswith(".ww3"):
        return lower != "grid.ww3"
    return False


def delete_all_under(workdir: str) -> tuple[int, list[str]]:
    """删除 workdir 下所有文件与空子目录（不删 workdir 本身）。"""
    errors: list[str] = []
    removed = 0
    for root, dirs, files in os.walk(workdir, topdown=False, followlinks=False):
        for name in files:
            path = os.path.join(root, name)
            try:
                os.remove(path)
                removed += 1
            except OSError as exc:
                errors.append(f"{path}: {exc}")
        for name in dirs:
            path = os.path.join(root, name)
            try:
                os.rmdir(path)
            except OSError as exc:
                errors.append(f"{path}: {exc}")
    return removed, errors


def delete_run_artifacts_under(workdir: str) -> tuple[int, list[str]]:
    """删除 workdir 下的运行产物（.ww3 除 grid.ww3 / .log / .bin）。"""
    errors: list[str] = []
    removed = 0
    for root, _dirs, files in os.walk(workdir, topdown=True, followlinks=False):
        for name in files:
            if not should_remove_run_artifact(name):
                continue
            path = os.path.join(root, name)
            try:
                os.remove(path)
                removed += 1
            except OSError as exc:
                errors.append(f"{path}: {exc}")
    return removed, errors
