"""Desktop startup for the workflow-backed application."""

from __future__ import annotations

import os
import sys
from typing import Any


def _select_initial_work_directory(window: Any) -> bool:
    """Prompt for a work directory on startup. Returns False if the user cancels."""
    from .windows.work_folder_dialog import WorkFolderDialog

    dialog = WorkFolderDialog(parent=window, is_startup=True)
    if dialog.exec() != dialog.DialogCode.Accepted or not dialog.selected_folder:
        return False
    if hasattr(window, "set_work_directory"):
        window.set_work_directory(dialog.selected_folder)
    return True


def create_window():
    from .windows.preprocessing_window import create_preprocessing_window

    return create_preprocessing_window()


def main(argv: list[str] | None = None) -> int:
    # 桌面 GUI 硬性依赖：PyQt6 + QtWebEngineCore（globe_picker 在模块顶层 import 它，
    # 缺失会在 import 链深处裸抛 ModuleNotFoundError）。统一在这里做友好检查。
    # [EN] Desktop requires PyQt6 + QtWebEngineCore (imported at module top by
    # globe_picker); check here so users get an install hint instead of a raw traceback.
    try:
        import PyQt6.QtCore  # noqa: F401
        from PyQt6.QtWidgets import QApplication  # noqa: F401
        import PyQt6.QtWebEngineCore  # noqa: F401
    except ImportError as exc:
        missing = getattr(exc, "name", "") or str(exc)
        print(
            f"无法启动桌面界面：缺少 GUI 依赖（{missing}）。\n"
            "请重新安装或升级 ww3tool（0.1.3 起 GUI 依赖已内置）：\n"
            "  pip install --upgrade ww3tool                     # pip 安装形态\n"
            "  python3 -m pip install -r src/requirements.txt    # 仓库形态\n"
            "（如果只是用命令行，无需 GUI：ww3tool --help / ww3tool shell）",
            file=sys.stderr,
        )
        return 1

    # [EN] Must set AA_ShareOpenGLContexts before QApplication for QWebEngineView.
    PyQt6.QtCore.QCoreApplication.setAttribute(
        PyQt6.QtCore.Qt.ApplicationAttribute.AA_ShareOpenGLContexts
    )

    # [EN] Validate root params.yml paths at startup (same as CLI/shell).
    # Incompatible or non-existent paths are auto-corrected before any config is loaded.
    try:
        from workflows.infrastructure.runtime_config import sanitize_root_params_paths
        sanitize_root_params_paths()
    except Exception:
        pass

    arguments = [sys.argv[0], *(argv if argv is not None else sys.argv[1:])]
    # Windows 无 GPU 环境（远程桌面 / 云主机）下 QtWebEngine 的 Chromium GPU
    # 进程会初始化失败，拖垮整个窗口渲染（白屏）。默认强制 ANGLE + SwiftShader
    # 软件渲染；用户已自定义 QTWEBENGINE_CHROMIUM_FLAGS 时尊重其设置。
    # [EN] On Windows GPU-less environments (RDP / cloud VMs) the QtWebEngine
    # Chromium GPU process fails and blanks the whole window. Default to
    # ANGLE + SwiftShader software rendering unless the user set their own flags.
    if sys.platform == "win32" and not os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS"):
        os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (
            "--disable-gpu --use-gl=angle --use-angle=swiftshader"
        )
    app = QApplication(arguments)
    from .branding import load_logo_icon, apply_window_logo

    icon = load_logo_icon()
    if icon is not None:
        app.setWindowIcon(icon)

    window = create_window()
    apply_window_logo(window)
    window.show()
    if not _select_initial_work_directory(window):
        return 0
    return app.exec()
