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
    # 缺失会在 import 链深处裸抛 ModuleNotFoundError）。统一在这里做友好检查，
    # 并**自动安装**缺失组件（pip 形态），不再要求用户手工补装。
    # [EN] Desktop requires PyQt6 + QtWebEngineCore. Check here and auto-install
    # the missing pieces (pip install) instead of asking the user to do it.
    _GUI_PACKAGES = ("PyQt6", "PyQt6-WebEngine", "PyQt6-Fluent-Widgets")

    def _gui_imports_ok() -> bool:
        try:
            import PyQt6.QtCore  # noqa: F401
            from PyQt6.QtWidgets import QApplication  # noqa: F401
            import PyQt6.QtWebEngineCore  # noqa: F401
            return True
        except ImportError:
            return False

    def _auto_install_gui() -> None:
        """自动安装缺失的 GUI 依赖（用当前解释器的 pip）。"""
        print("检测到缺少桌面 GUI 依赖，正在自动安装（首次约需下载 200MB，请稍候）...")
        try:
            import subprocess

            subprocess.run(
                [sys.executable, "-m", "pip", "install", "--upgrade", *_GUI_PACKAGES],
                check=True,
                timeout=900,
            )
            print("GUI 依赖安装完成。")
        except Exception as exc:  # noqa: BLE001 - 任何失败都走提示路径
            print(f"自动安装失败：{exc}", file=sys.stderr)

    if not _gui_imports_ok():
        _auto_install_gui()
        if not _gui_imports_ok():
            # 包已装但 import 仍失败（通常是 Windows DLL 加载问题）：
            # 打印真实异常细节，便于定位（缺 VC++ 运行库 / 版本冲突等）。
            # [EN] Packages installed but import still fails (usually a Windows
            # DLL loading issue): print the real exception for diagnosis.
            import traceback

            print("导入 QtWebEngineCore 失败，详细错误：", file=sys.stderr)
            try:
                import PyQt6.QtWebEngineCore  # noqa: F401
            except ImportError:
                traceback.print_exc()
            print(
                "\n无法启动桌面界面：GUI 依赖已安装但加载失败（见上方错误）。\n"
                "Windows 常见原因与解决：\n"
                "  1. 缺 Microsoft Visual C++ 运行库：\n"
                "     下载安装 https://aka.ms/vs/17/release/vc_redist.x64.exe\n"
                "  2. 或重装 Qt 组件：pip install --force-reinstall PyQt6-WebEngine PyQt6\n"
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
        # 只用 ANGLE + SwiftShader 软件渲染；不要再加 --disable-gpu/--use-gl=angle
        # （两者与 ANGLE 冲突，Chromium 会告警且仍白屏）。
        os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--use-angle=swiftshader"
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
