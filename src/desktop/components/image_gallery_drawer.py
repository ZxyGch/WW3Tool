"""右侧图片抽屉组件（网格可视化、绘图结果等共用）。

在父窗口右侧悬浮展示 PNG 列表，点击遮罩关闭；样式与交互对齐 src 第二步
网格可视化的侧边抽屉。
"""

from __future__ import annotations

import threading
from pathlib import Path

from PyQt6.QtCore import QEasingCurve, QObject, QPropertyAnimation, QRect, QTimer, Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices, QImage, QPainter, QPainterPath, QPixmap
from PyQt6.QtWidgets import (
    QFrame,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import isDarkTheme
from workflows.support.translations import tr

class _GalleryImageLoader(QObject):
    """在后台线程解码图片，经 Qt 信号回到主线程构建 UI。"""

    loaded = pyqtSignal(str, list)

    def start(self, title: str, image_paths: list[str]) -> None:
        threading.Thread(
            target=self._load,
            args=(title, image_paths),
            daemon=True,
        ).start()

    def _load(self, title: str, image_paths: list[str]) -> None:
        items: list[tuple[str, QImage]] = []
        for path_str in image_paths:
            path = Path(path_str)
            if not path.is_file():
                continue
            image = QImage(str(path))
            if not image.isNull():
                items.append((str(path), image))
        self.loaded.emit(title, items)


class _ClickableImage(QLabel):
    """按面板宽度等比缩放显示，点击打开原图。"""

    def __init__(self, path: str, source: QImage | None = None) -> None:
        super().__init__()
        self._path = path
        if source is not None and not source.isNull():
            self._src = QPixmap.fromImage(source)
        else:
            self._src = QPixmap(path)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet("border: none; background-color: palette(window);")
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._radius = 8

    def rescale(self, width: int):
        if self._src.isNull():
            self.setText(tr("plotting_load_image_failed_short", "无法加载图片"))
            return self.sizeHint()
        target = max(50, width)
        scaled = self._src.scaledToWidth(target, Qt.TransformationMode.SmoothTransformation)
        self.setPixmap(_rounded_pixmap(scaled, self._radius))
        self.setFixedSize(scaled.size())
        return scaled.size()

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt override)
        QDesktopServices.openUrl(QUrl.fromLocalFile(self._path))


class ImageGalleryPanel(QWidget):
    """右侧抽屉内的图片列表面板。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._images: list[_ClickableImage] = []
        self._cards: list[tuple[QFrame, _ClickableImage, QLabel]] = []
        self._loader = _GalleryImageLoader()
        self._loader.loaded.connect(self._populate_images)
        self.setObjectName("imageGalleryPanel")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 0, 0, 0)
        layout.setSpacing(0)

        self._header = QFrame()
        self._header.setObjectName("imageGalleryHeader")
        header_layout = QVBoxLayout(self._header)
        header_layout.setContentsMargins(0, 10, 15, 8)
        header_layout.setSpacing(0)
        self._title_label = QLabel()
        self._title_label.setWordWrap(True)
        header_layout.addWidget(self._title_label)
        self._header.hide()
        layout.addWidget(self._header)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        bg = self._background_color()
        self._scroll.setStyleSheet(
            f"QScrollArea {{ background-color: {bg}; border: none; }}"
            f"QScrollArea > QWidget > QWidget {{ background-color: {bg}; }}"
        )
        self._content = QWidget()
        self._content.setStyleSheet(f"background-color: {bg}; border: none;")
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(0, 0, 0, 20)
        self._content_layout.setSpacing(20)
        self._content_layout.addStretch(1)
        self._content.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)
        self._scroll.setWidget(self._content)
        layout.addWidget(self._scroll, 1)
        self._apply_drawer_style()

    def show_images(self, title: str, image_paths: list[str]) -> None:
        if title:
            self._title_label.setText(title)
            self._header.show()
        else:
            self._header.hide()

        self._clear_cards()
        self._loader.start(title, image_paths)

    def _clear_cards(self) -> None:
        while self._content_layout.count() > 1:
            item = self._content_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._images = []
        self._cards = []

    def _populate_images(self, title: str, items: list) -> None:
        if title:
            self._title_label.setText(title)
            self._header.show()
        else:
            self._header.hide()
        self._clear_cards()

        for item in items:
            if isinstance(item, tuple) and len(item) == 2:
                path_str, source = item
            else:
                path_str, source = str(item), None
            path = Path(path_str)
            frame = QFrame()
            frame.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            frame.setStyleSheet(
                """
                QFrame {
                    border: 1px solid #ccc;
                    border-radius: 4px;
                    background-color: white;
                }
                """
            )
            frame_layout = QVBoxLayout(frame)
            frame_layout.setContentsMargins(15, 8, 8, 8)
            frame_layout.setSpacing(5)

            image = _ClickableImage(str(path), source if isinstance(source, QImage) else None)
            frame_layout.addWidget(image, 0, Qt.AlignmentFlag.AlignCenter)
            name_label = QLabel(path.name)
            name_label.setWordWrap(True)
            name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            name_label.setStyleSheet("font-size: 12px; color: #666; border: none; background: transparent;")
            name_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            frame_layout.addWidget(name_label)
            self._images.append(image)
            self._cards.append((frame, image, name_label))
            self._content_layout.insertWidget(
                self._content_layout.count() - 1,
                frame,
                0,
                Qt.AlignmentFlag.AlignTop,
            )
        self._rescale_images()

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        super().resizeEvent(event)
        self._rescale_images()

    def _rescale_images(self) -> None:
        content_width = max(80, self._scroll.viewport().width())
        self._content.setFixedWidth(content_width)
        card_width = content_width
        horizontal_margins = 15 + 8
        vertical_margins = 8 + 8
        label_spacing = 5
        image_width = max(50, card_width - horizontal_margins - 2)
        for frame, image, name_label in self._cards:
            image_size = image.rescale(image_width)
            name_label.setFixedWidth(image_width)
            label_height = name_label.heightForWidth(image_width)
            if label_height <= 0:
                label_height = name_label.sizeHint().height()
            name_label.setFixedHeight(label_height)
            frame_height = image_size.height() + label_height + vertical_margins + label_spacing + 2
            frame.setFixedSize(card_width, frame_height)

    def _apply_drawer_style(self) -> None:
        bg = self._background_color()
        color = "#FFFFFF" if isDarkTheme() else "#222222"
        panel_style = (
            f"QWidget#imageGalleryPanel {{ background-color: {bg}; }}"
            f"QFrame#imageGalleryHeader {{ background-color: {bg}; border: none; }}"
            f"QLabel {{ background-color: {bg}; color: {color}; border: none; }}"
        )
        self.setStyleSheet(panel_style)
        self._title_label.setStyleSheet(
            f"font-size: 14px; font-weight: 600; color: {color};"
            f" background-color: {bg}; border: none; padding: 0;"
        )
        self._scroll.setStyleSheet(
            f"QScrollArea {{ background-color: {bg}; border: none; }}"
            f"QScrollArea > QWidget > QWidget {{ background-color: {bg}; }}"
        )
        self._content.setStyleSheet(f"background-color: {bg}; border: none;")

    def _background_color(self) -> str:
        return "#2d2d2d" if isDarkTheme() else "#f5f5f5"

# 程序打开侧栏后短暂忽略点击，避免按钮 mouse release 落在透明层上立刻关闭。
_CLICK_GUARD_MS = 450


class ImageGalleryDrawer(QWidget):
    """覆盖父窗口的透明事件层，右侧滑入图片抽屉；点击面板外区域关闭。"""

    def __init__(self, parent: QWidget | None = None, *, on_close=None) -> None:
        super().__init__(parent)
        self._on_close = on_close
        self._host_rect = QRect()
        self._is_open = False
        self._animation_token = 0
        self._click_guard_timer = QTimer(self)
        self._click_guard_timer.setSingleShot(True)
        self._click_guard_timer.timeout.connect(self._end_click_guard)

        self._panel = ImageGalleryPanel(self)
        self._panel.hide()

        self._animation = QPropertyAnimation(self._panel, b"geometry", self)
        self._animation.setDuration(300)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.hide()

    def sync_host_geometry(self, host_rect: QRect) -> None:
        """根据父容器尺寸更新抽屉布局。"""
        self._host_rect = QRect(host_rect)
        if not self._host_rect.isValid():
            return
        if self._is_open:
            self.setGeometry(self._host_rect)
            self._position_panel(animated=False)

    def show_images(self, title: str, image_paths: list[str]) -> None:
        if not image_paths:
            return
        # 推迟到当前按钮 click 处理完再展开，避免 release 落在本层上触发关闭。
        QTimer.singleShot(0, lambda: self._open_gallery_impl(title, image_paths))

    def hide_gallery(self) -> None:
        if self._is_open:
            self._close_drawer()
            return
        self._panel.hide()
        self.hide()
        if callable(self._on_close):
            self._on_close()

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        super().resizeEvent(event)
        if self._is_open:
            self._position_panel(animated=False)

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt override)
        if self._click_guard_timer.isActive():
            event.accept()
            return
        if self._is_open and not self._panel.geometry().contains(event.position().toPoint()):
            self.hide_gallery()
            event.accept()
            return
        super().mousePressEvent(event)

    def _begin_click_guard(self) -> None:
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._click_guard_timer.start(_CLICK_GUARD_MS)

    def _end_click_guard(self) -> None:
        if self._is_open:
            self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)

    def _cancel_panel_animation(self) -> None:
        self._animation_token += 1
        if self._animation.state() == QPropertyAnimation.State.Running:
            self._animation.stop()
        try:
            self._animation.finished.disconnect()
        except TypeError:
            pass

    def _open_gallery_impl(self, title: str, image_paths: list[str]) -> None:
        if self.parent() is not None:
            self.sync_host_geometry(self.parent().rect())
        elif not self._host_rect.isValid():
            return
        self._cancel_panel_animation()
        self.setGeometry(self._host_rect)
        self._begin_click_guard()
        self._panel.show_images(title, image_paths)
        self.show()
        self.raise_()
        self._panel.show()
        self._panel.raise_()
        if self._is_open:
            self._position_panel(animated=False)
            QTimer.singleShot(0, self._panel._rescale_images)
            return
        self._open_drawer()
        QTimer.singleShot(0, self._panel._rescale_images)

    def _drawer_width(self) -> int:
        return max(340, self.width() // 2)

    def _position_panel(self, *, animated: bool) -> None:
        panel_width = self._drawer_width()
        height = self.height()
        if self._is_open:
            end_rect = QRect(self.width() - panel_width, 0, panel_width, height)
        else:
            end_rect = QRect(self.width(), 0, panel_width, height)
        if animated:
            self._animation.setStartValue(self._panel.geometry())
            self._animation.setEndValue(end_rect)
            self._animation.start()
        else:
            self._panel.setGeometry(end_rect)

    def _open_drawer(self) -> None:
        if self._is_open:
            self._position_panel(animated=False)
            return
        self._cancel_panel_animation()
        panel_width = self._drawer_width()
        height = self.height()
        start_rect = QRect(self.width(), 0, panel_width, height)
        end_rect = QRect(self.width() - panel_width, 0, panel_width, height)
        self._panel.setGeometry(start_rect)
        self._is_open = True
        self._animation.setStartValue(start_rect)
        self._animation.setEndValue(end_rect)
        self._animation.start()

    def _close_drawer(self) -> None:
        if not self._is_open:
            self.hide_gallery()
            return
        self._click_guard_timer.stop()
        self._end_click_guard()
        panel_width = self._drawer_width()
        height = self.height()
        start_rect = self._panel.geometry()
        end_rect = QRect(self.width(), 0, panel_width, height)
        self._is_open = False

        def _finish() -> None:
            if close_token != self._animation_token:
                return
            self._panel.hide()
            self.hide()
            if callable(self._on_close):
                self._on_close()

        self._cancel_panel_animation()
        close_token = self._animation_token
        self._animation.finished.connect(_finish)
        self._animation.setStartValue(start_rect)
        self._animation.setEndValue(end_rect)
        self._animation.start()


class ImageGalleryHost:
    """可混入任意窗口，提供统一的右侧图片抽屉绑定与展示 API。"""

    _image_gallery: ImageGalleryDrawer | None = None
    _image_gallery_parent: QWidget | None = None

    def bind_image_gallery(self, parent: QWidget) -> ImageGalleryDrawer:
        self._image_gallery_parent = parent
        self._image_gallery = ImageGalleryDrawer(parent)
        self._image_gallery.sync_host_geometry(parent.rect())
        self._image_gallery.hide()
        return self._image_gallery

    def sync_image_gallery_geometry(self) -> None:
        gallery = getattr(self, "_image_gallery", None)
        host_parent = getattr(self, "_image_gallery_parent", None)
        if gallery is not None and host_parent is not None:
            gallery.sync_host_geometry(host_parent.rect())

    def show_image_gallery(self, title: str, image_paths: list[str]) -> None:
        gallery = getattr(self, "_image_gallery", None)
        if gallery is None or not image_paths:
            return
        self.sync_image_gallery_geometry()
        gallery.show_images(title, image_paths)

    def hide_image_gallery(self) -> None:
        gallery = getattr(self, "_image_gallery", None)
        if gallery is not None:
            gallery.hide_gallery()


def _rounded_pixmap(pixmap: QPixmap, radius: int) -> QPixmap:
    rounded = QPixmap(pixmap.size())
    rounded.fill(Qt.GlobalColor.transparent)
    painter = QPainter(rounded)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(0, 0, pixmap.width(), pixmap.height(), radius, radius)
    painter.setClipPath(path)
    painter.drawPixmap(0, 0, pixmap)
    painter.end()
    return rounded
