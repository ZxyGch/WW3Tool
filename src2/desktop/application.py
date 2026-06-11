"""Desktop startup for the workflow-backed application."""

from __future__ import annotations

import sys
from pathlib import Path


def create_window():
    from .windows.full_application_window import create_full_application_window

    return create_full_application_window()


def main(argv: list[str] | None = None) -> int:
    try:
        from PyQt6.QtGui import QIcon
        from PyQt6.QtWidgets import QApplication
    except ImportError as exc:
        raise SystemExit(
            "无法启动桌面界面：请先安装 PyQt6 依赖 "
            "(python3 -m pip install -r src2/requirements.txt)"
        ) from exc

    arguments = [sys.argv[0], *(argv if argv is not None else sys.argv[1:])]
    app = QApplication(arguments)
    icon = Path(__file__).resolve().parents[2] / "public" / "resource" / "logo.png"
    if icon.exists():
        app.setWindowIcon(QIcon(str(icon)))

    from .windows.full_application_window import select_initial_work_directory

    window = create_window()
    window.show()
    if not select_initial_work_directory(window):
        return 0
    return app.exec()
