"""Backward-compatible exports for the shared image gallery drawer."""

from .image_gallery_drawer import (
    ImageGalleryDrawer,
    ImageGalleryHost,
    ImageGalleryPanel,
)

GridImagePanel = ImageGalleryPanel
FloatingGalleryOverlay = ImageGalleryDrawer

__all__ = [
    "GridImagePanel",
    "FloatingGalleryOverlay",
    "ImageGalleryDrawer",
    "ImageGalleryHost",
    "ImageGalleryPanel",
]
