"""Desktop dialog for map and grid preview images."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices, QPixmap
from PyQt6.QtWidgets import QDialog, QFrame, QGridLayout, QLabel, QScrollArea, QVBoxLayout, QWidget
from workflows.support.translations import tr


class ImagePreviewDialog(QDialog):
    """Show one or more generated preview images in a scrollable dialog."""

    def __init__(self, title: str, image_paths: list[str], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(1260, 900)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        grid = QGridLayout(content)
        grid.setSpacing(10)
        grid.setContentsMargins(10, 10, 10, 10)

        for index, image_path in enumerate(image_paths):
            path = Path(image_path)
            frame = QFrame()
            frame.setStyleSheet(
                "QFrame { border: 1px solid rgba(128,128,128,0.35); border-radius: 4px; }"
            )
            layout = QVBoxLayout(frame)
            caption = QLabel(_caption(path))
            caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
            caption.setStyleSheet("font-weight: 600; border: none;")
            layout.addWidget(caption)

            image = QLabel()
            image.setAlignment(Qt.AlignmentFlag.AlignCenter)
            image.setStyleSheet("border: none;")
            pixmap = QPixmap(str(path))
            image.setPixmap(
                pixmap.scaled(
                    1180 if len(image_paths) == 1 else 580,
                    760 if len(image_paths) == 1 else 430,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
            image.setCursor(Qt.CursorShape.PointingHandCursor)
            image.mousePressEvent = lambda _event, image_path=str(path): QDesktopServices.openUrl(
                QUrl.fromLocalFile(image_path)
            )
            layout.addWidget(image)
            grid.addWidget(frame, index // 2 if len(image_paths) > 1 else index, index % 2 if len(image_paths) > 1 else 0)

        scroll.setWidget(content)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(scroll)


def _caption(path: Path) -> str:
    if path.name.endswith("_region_map.png"):
        return tr("step2_map_range_label", "网格范围")
    titles = {
        "grid_bathymetry.png": tr("grid_image_bathymetry", "Bathymetry"),
        "grid_structure.png": tr("grid_image_structure", "Grid Structure"),
        "grid_mask.png": tr("grid_image_mask", "Land-Sea Mask"),
        "grid_obstruction_x.png": tr("grid_image_obstruction_x", "Sx Obstruction"),
        "grid_obstruction_y.png": tr("grid_image_obstruction_y", "Sy Obstruction"),
    }
    return titles.get(path.name, path.stem.replace("_", " ").title())
