"""Input validators shared by desktop forms."""

from __future__ import annotations

from PyQt6.QtCore import QRegularExpression
from PyQt6.QtGui import QDoubleValidator, QIntValidator, QRegularExpressionValidator


def int_validator(bottom: int = 0, top: int = 2_147_483_647) -> QIntValidator:
    return QIntValidator(bottom, top)


def double_validator(
    bottom: float = -1.0e12,
    top: float = 1.0e12,
    *,
    decimals: int = 12,
) -> QDoubleValidator:
    validator = QDoubleValidator(bottom, top, decimals)
    validator.setNotation(QDoubleValidator.Notation.StandardNotation)
    return validator


def date_yyyymmdd_validator() -> QRegularExpressionValidator:
    return QRegularExpressionValidator(QRegularExpression(r"\d{0,8}"))


def datetime_yyyymmdd_hhmmss_validator() -> QRegularExpressionValidator:
    return QRegularExpressionValidator(QRegularExpression(r"\d{0,8}( \d{0,6})?"))
