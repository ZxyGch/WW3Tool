"""Work directory selection dialog for the src2 desktop shell."""

from __future__ import annotations

import datetime
import os
import sys
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QApplication, QFileDialog, QHBoxLayout, QLabel, QWidget
from qfluentwidgets import InfoBar, LineEdit, MessageBoxBase, PrimaryPushButton

from workflows.infrastructure.runtime_config import (
    add_recent_workdir,
    get_default_workdir,
    get_recent_workdirs,
    order_recent_workdirs_for_display,
)
from workflows.support.translations import tr


class WorkFolderDialog(MessageBoxBase):
    """Choose or create a work directory before preprocessing."""

    finished = pyqtSignal()

    def __init__(
        self,
        parent=None,
        *,
        is_startup: bool = False,
        current_folder: str | None = None,
    ) -> None:
        super().__init__(parent)
        self.is_startup = is_startup
        self.current_folder = current_folder
        self.selected_folder: str | None = None
        self.success_message: tuple[str, str] | None = None
        self._finished_emitted = False
        self.hideYesButton()
        self.hideCancelButton()
        if hasattr(self, "buttonLayout") and self.buttonLayout.parent():
            self.buttonLayout.parent().setVisible(False)
        self._build_surface()

    def _parent_style(self, *method_names: str) -> str:
        parent = self.parent()
        for name in method_names:
            method = getattr(parent, name, None)
            if callable(method):
                return method()
        return ""

    def _build_surface(self) -> None:
        name_row = QHBoxLayout()
        name_row.addWidget(QLabel(tr("workdir_dialog_new_name", "新工作目录名称：")))
        self.name_edit = LineEdit()
        self.name_edit.setText(datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S"))
        self.name_edit.setPlaceholderText(tr("workdir_dialog_name_placeholder", "输入工作目录名称"))
        self.name_edit.setMinimumWidth(200)
        self.name_edit.setStyleSheet(self._parent_style("_input_style", "_get_input_style"))
        name_row.addWidget(self.name_edit, 1)
        self.viewLayout.addLayout(name_row)

        self._add_recent_workdirs_section()

        button_style = self._parent_style("_button_style", "_get_button_style")
        self.btn_create = PrimaryPushButton(tr("workdir_dialog_create", "创建新工作目录"))
        self.btn_create.setStyleSheet(button_style)
        self.btn_create.clicked.connect(self.create_new)
        self.viewLayout.addWidget(self.btn_create)

        self.btn_choose = PrimaryPushButton(tr("workdir_dialog_choose", "选择已有工作目录"))
        self.btn_choose.setStyleSheet(button_style)
        self.btn_choose.clicked.connect(self.choose_existing)
        self.viewLayout.addWidget(self.btn_choose)

        self.btn_cancel = PrimaryPushButton(tr("cancel", "取消"))
        self.btn_cancel.setStyleSheet(button_style)
        self.btn_cancel.clicked.connect(self._cancel_dialog)
        self.viewLayout.addWidget(self.btn_cancel)

    def _add_recent_workdirs_section(self) -> None:
        recent_dirs = order_recent_workdirs_for_display(
            get_recent_workdirs(),
            current_folder=self.current_folder,
        )
        if not recent_dirs:
            return

        separator = QWidget()
        separator.setFixedHeight(1)
        separator.setStyleSheet("background-color: rgba(128, 128, 128, 0.3);")
        self.viewLayout.addWidget(separator)

        recent_label = QLabel(tr("workdir_dialog_recent", "最近打开的工作目录："))
        recent_label.setStyleSheet("font-weight: normal; margin-top: 8px; margin-bottom: 4px;")
        self.viewLayout.addWidget(recent_label)

        names = [os.path.basename(path) for path in recent_dirs]
        has_duplicate_names = len(names) != len(set(names))
        for folder in recent_dirs:
            container = QWidget()
            container.setCursor(Qt.CursorShape.PointingHandCursor)
            container.setToolTip(folder)
            container.setAttribute(Qt.WidgetAttribute.WA_AcceptTouchEvents, False)
            container.setMouseTracking(True)
            container.setStyleSheet(
                """
                QWidget {
                    background-color: rgba(128, 128, 128, 0.1);
                    border: 1px solid rgba(128, 128, 128, 0.3);
                    border-radius: 6px;
                    padding: 8px 12px;
                }
                """
            )
            row = QHBoxLayout(container)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(8)
            icon = QLabel("📁")
            icon.setStyleSheet("font-size: 13px; border: none; background: transparent;")
            label = QLabel(folder if has_duplicate_names else os.path.basename(folder))
            label.setStyleSheet("font-size: 13px; border: none; background: transparent;")
            label.setWordWrap(False)
            row.addWidget(icon)
            row.addStretch()
            row.addWidget(label)
            container.mousePressEvent = self._recent_click_handler(folder)
            self.viewLayout.addWidget(container)

    def _recent_click_handler(self, folder: str):
        def choose(event) -> None:
            if event.button() == Qt.MouseButton.LeftButton:
                self._choose(folder)

        return choose

    def create_new(self) -> None:
        name = self.name_edit.text().strip()
        if not name:
            InfoBar.warning(
                title=tr("tip", "提示"),
                content=tr("workdir_dialog_enter_name", "请输入文件夹名称"),
                duration=2000,
                parent=self,
            )
            return

        base = get_default_workdir(create_if_not_exists=True)
        if not base:
            InfoBar.error(
                title=tr("workdir_dialog_create_failed", "创建失败"),
                content=tr("workdir_dialog_cannot_create_short", "无法创建默认工作目录"),
                duration=3000,
                parent=self,
            )
            return

        target = os.path.abspath(os.path.normpath(os.path.join(base, name)))
        if os.path.exists(target):
            InfoBar.error(
                title=tr("workdir_dialog_exists", "文件夹已存在"),
                content=tr("workdir_dialog_exists_content", "文件夹已存在，无法创建：{path}").format(path=target),
                duration=3000,
                parent=self,
            )
            return

        try:
            os.makedirs(target, exist_ok=False)
        except OSError as exc:
            InfoBar.error(
                title=tr("workdir_dialog_create_failed", "创建失败"),
                content=tr("workdir_dialog_create_error", "创建文件夹失败：{error}").format(error=exc),
                duration=3000,
                parent=self,
            )
            return

        self._choose(target, success_text=tr("workdir_dialog_create_success_content", "文件夹已成功创建：{path}").format(path=target))

    def choose_existing(self) -> None:
        start = get_default_workdir(create_if_not_exists=False) or str(Path.cwd())
        selected = QFileDialog.getExistingDirectory(
            self,
            tr("workdir_dialog_select_title", "选择已有文件夹"),
            start,
            QFileDialog.Option.ShowDirsOnly | QFileDialog.Option.DontResolveSymlinks,
        )
        if selected:
            self._choose(selected, success_text=tr("workdir_dialog_choose_success_content", "已选择文件夹：{path}").format(path=selected))

    def _choose(self, folder: str, success_text: str | None = None) -> None:
        folder = os.path.abspath(os.path.normpath(folder))
        if not os.path.isdir(folder):
            InfoBar.warning(
                title=tr("workdir_dialog_not_exists", "目录不存在"),
                content=tr("workdir_dialog_not_exists_content", "目录已不存在：{path}").format(path=folder),
                duration=2000,
                parent=self,
            )
            return
        self.selected_folder = folder
        add_recent_workdir(folder)
        if success_text:
            self.success_message = (tr("workdir_dialog_choose_success", "选择成功"), success_text)
        if success_text:
            InfoBar.success(
                title=tr("workdir_dialog_choose_success", "选择成功"),
                content=success_text,
                duration=2000,
                parent=self.parent() or self,
            )
        self.accept()
        self._emit_finished()

    def _cancel_dialog(self) -> None:
        self.selected_folder = None
        if self.is_startup:
            self.reject()
            app = QApplication.instance()
            if app is not None:
                app.quit()
            sys.exit(0)
        self.reject()

    def reject(self) -> None:
        if self.is_startup:
            self.selected_folder = None
        super().reject()
        self._emit_finished()

    def _emit_finished(self) -> None:
        if self._finished_emitted:
            return
        self._finished_emitted = True
        self.finished.emit()
