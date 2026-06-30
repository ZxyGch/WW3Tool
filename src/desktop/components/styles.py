"""主题感知的控件样式表（供设置页等复用）。

与 :class:`preprocessing_window.PreprocessingWindow` 内联样式保持一致，集中一处
便于复用与统一。主题判断使用 qfluentwidgets ``isDarkTheme``。

[EN] Theme-aware control stylesheets (shared by the settings page and others).

Kept consistent with the inline styles in
:class:`preprocessing_window.PreprocessingWindow`, centralized here for easy
reuse and uniformity. Theme detection uses qfluentwidgets ``isDarkTheme``.
"""

from __future__ import annotations


def is_dark() -> bool:
    try:
        from qfluentwidgets import isDarkTheme

        return bool(isDarkTheme())
    except Exception:
        return False


def input_style() -> str:
    if is_dark():
        return """
            LineEdit, EditableComboBox {
                background-color: #2D2D2D; border: 1px solid #404040;
                border-radius: 4px; padding: 4px 8px; color: #FFFFFF;
            }
            LineEdit:focus, EditableComboBox:focus { border: 1px solid #404040; }
            LineEdit:read-only, EditableComboBox:read-only {
                background-color: #2D2D2D; border: 1px solid #404040;
                color: #FFFFFF;
            }
        """
    return """
        LineEdit, EditableComboBox {
            background-color: #FFFFFF; border: 1px solid #D0D0D0;
            border-radius: 4px; padding: 4px 8px; color: #000000;
        }
        LineEdit:focus, EditableComboBox:focus { border: 1px solid #D0D0D0; }
        LineEdit:read-only, EditableComboBox:read-only {
            background-color: #FFFFFF; border: 1px solid #D0D0D0;
            color: #000000;
        }
    """


def combo_style() -> str:
    if is_dark():
        return """
            ComboBox {
                background-color: #2D2D2D; border: 1px solid #404040;
                border-radius: 4px; padding: 4px 8px; color: #FFFFFF;
                text-align: left;
            }
            ComboBox:disabled { color: #FFFFFF; }
        """
    return """
        ComboBox {
            background-color: #FFFFFF; border: 1px solid #D0D0D0;
            border-radius: 4px; padding: 4px 8px; color: #000000;
            text-align: left;
        }
        ComboBox:disabled { color: #000000; }
    """


def label_style(*, extra: str = "") -> str:
    """主题感知的字段标签样式（直接设在 QLabel 上，勿用类型选择器）。

    [EN] Theme-aware field label style (apply directly to QLabel; do not use
    a type selector).
    """
    color = "#FFFFFF" if is_dark() else "#000000"
    parts = [f"color: {color};"]
    if extra:
        parts.append(extra)
    return " ".join(parts)


def section_title_style() -> str:
    color = "#FFFFFF" if is_dark() else "#000000"
    return f"font-weight: normal; font-size: 14px; color: {color};"


def button_style() -> str:
    if is_dark():
        return """
            PrimaryPushButton {
                background-color: #2D2D2D; border: 1px solid #404040;
                border-radius: 4px; min-height: 20px; padding: 8px 16px; color: #FFFFFF;
            }
            PrimaryPushButton:hover { background-color: #3D3D3D; }
            PrimaryPushButton:pressed { background-color: #353535; }
            PrimaryPushButton:disabled { background-color: #1D1D1D; color: #666666; }
        """
    return """
        PrimaryPushButton {
            background-color: #F5F5F5; border: 1px solid #E0E0E0;
            border-radius: 4px; min-height: 20px; padding: 8px 16px;
        }
        PrimaryPushButton:hover { background-color: #EEEEEE; }
        PrimaryPushButton:pressed { background-color: #E8E8E8; }
        PrimaryPushButton:disabled { background-color: #E0E0E0; color: #999999; }
    """
