"""
Home package exports.

Keep package import side effects minimal so submodules can be imported
independently without triggering the entire UI tree during package init.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

__all__ = [
    "HomeStepOneCard",
    "HomeStepTwoCard",
    "HomeStepThreeCard",
    "HomeStepFourCard",
    "HomeLocalRun",
    "HomeStepFiveCard",
    "HomeState",
]


if TYPE_CHECKING:
    from .home_local_run import HomeLocalRun
    from .step1.step1_ui import HomeStepOneCard
    from .step2.step2_ui import HomeStepTwoCard
    from .step3.step3_ui import HomeStepThreeCard
    from .step4.step4_ui import HomeStepFourCard
    from .step5.step5_ui import HomeStepFiveCard
    from .utils import HomeState


_LAZY_IMPORTS = {
    "HomeStepOneCard": ("home.step1.step1_ui", "HomeStepOneCard"),
    "HomeStepTwoCard": ("home.step2.step2_ui", "HomeStepTwoCard"),
    "HomeStepThreeCard": ("home.step3.step3_ui", "HomeStepThreeCard"),
    "HomeStepFourCard": ("home.step4.step4_ui", "HomeStepFourCard"),
    "HomeLocalRun": ("home.home_local_run", "HomeLocalRun"),
    "HomeStepFiveCard": ("home.step5.step5_ui", "HomeStepFiveCard"),
    "HomeState": ("home.utils", "HomeState"),
}


def __getattr__(name: str):
    if name not in _LAZY_IMPORTS:
        raise AttributeError(f"module 'home' has no attribute {name!r}")

    module_name, attr_name = _LAZY_IMPORTS[name]
    module = __import__(module_name, fromlist=[attr_name])
    value = getattr(module, attr_name)
    globals()[name] = value
    return value
