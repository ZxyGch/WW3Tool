"""强迫场（forcing）选择与路径状态模型。

本模块属于 ``domain/`` 领域层，定义强迫场类型枚举及 Step 1 相关状态容器，
供无界面 CLI 与 Desktop 预处理流程共用，避免 UI 与业务逻辑耦合。

主要消费者：
- ``application/forcing_preparation.py``：强迫场准备用例
- ``application/forcing_inspection.py``：文件检测与自动关联
- ``desktop/view_models/forcing_step.py``：桌面端 Step 1 视图模型

[EN] Forcing field selection and path state models.

This module belongs to the ``domain/`` layer and defines forcing field type
enumerations and Step 1 related state containers, shared by the headless CLI
and Desktop preprocessing workflows to avoid coupling UI with business logic.

Main consumers:
- ``application/forcing_preparation.py``: forcing preparation use case
- ``application/forcing_inspection.py``: file detection and auto-association
- ``desktop/view_models/forcing_step.py``: desktop Step 1 view model
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ForcingField(str, Enum):
    """WW3 强迫场类型枚举。

    成员值与 ``Step1Files`` 及 ``ForcingConfig`` 中的字段名一致。

    [EN] WW3 forcing field type enumeration.

    Member values correspond to field names in ``Step1Files`` and ``ForcingConfig``.
    """

    WIND = "wind"
    CURRENT = "current"
    LEVEL = "level"
    ICE = "ice"


# 强迫场在 UI 与批处理中的固定展示/遍历顺序
# [EN] Fixed display/iteration order for forcing fields in UI and batch processing
FORCING_FIELD_ORDER = (
    ForcingField.WIND,
    ForcingField.CURRENT,
    ForcingField.LEVEL,
    ForcingField.ICE,
)


@dataclass
class Step1Files:
    """各强迫场类型对应的源文件路径。

    路径以字符串形式存储（通常为绝对路径），未选择时为 ``None``。

    [EN] Source file paths for each forcing field type.

    Paths are stored as strings (typically absolute paths); ``None`` when not selected.
    """

    wind: Optional[str] = None
    current: Optional[str] = None
    level: Optional[str] = None
    ice: Optional[str] = None

    def get(self, forcing_field: ForcingField) -> Optional[str]:
        """按强迫场类型读取路径。

        Args:
            forcing_field: 目标强迫场枚举值。

        Returns:
            对应文件路径；未设置时返回 ``None``。

        [EN] Read the path by forcing field type.

        Args:
            forcing_field: Target forcing field enum value.

        Returns:
            Corresponding file path; returns ``None`` if not set.
        """
        return getattr(self, forcing_field.value)

    def set(self, forcing_field: ForcingField, path: Optional[str]) -> None:
        """按强迫场类型写入或清空路径。

        Args:
            forcing_field: 目标强迫场枚举值。
            path: 文件路径；``None`` 表示清除。

        [EN] Write or clear the path by forcing field type.

        Args:
            forcing_field: Target forcing field enum value.
            path: File path; ``None`` means clear.
        """
        setattr(self, forcing_field.value, path)

    def clear(self, forcing_field: Optional[ForcingField] = None) -> None:
        """清除一个或全部强迫场路径。

        Args:
            forcing_field: 指定要清除的场类型；``None`` 时清空全部四类路径。

        [EN] Clear one or all forcing field paths.

        Args:
            forcing_field: Field type to clear; when ``None``, clears all four field paths.
        """
        if forcing_field is None:
            for field_name in FORCING_FIELD_ORDER:
                self.set(field_name, None)
            return
        self.set(forcing_field, None)

    def copy(self) -> "Step1Files":
        """返回当前路径映射的浅拷贝。

        [EN] Return a shallow copy of the current path mapping.
        """
        return Step1Files(wind=self.wind, current=self.current, level=self.level, ice=self.ice)

    def existing_items(self) -> list[tuple[ForcingField, str]]:
        """列出所有已配置（非空）的强迫场及其路径。

        Returns:
            ``(ForcingField, path)`` 元组列表，顺序遵循 ``FORCING_FIELD_ORDER``。

        [EN] List all configured (non-empty) forcing fields and their paths.

        Returns:
            List of ``(ForcingField, path)`` tuples, ordered by ``FORCING_FIELD_ORDER``.
        """
        return [
            (forcing_field, path)
            for forcing_field in FORCING_FIELD_ORDER
            if (path := self.get(forcing_field))
        ]


@dataclass
class Step1State:
    """Step 1（强迫场准备）的完整运行时状态。

    聚合目录选择、各场文件路径、处理进度标志及处理模式等 UI/工作流共享字段。

    [EN] Complete runtime state for Step 1 (forcing preparation).

    Aggregates folder selection, per-field file paths, processing progress flags,
    and processing mode — fields shared by UI and workflow.
    """

    selected_folder: Optional[str] = None
    files: Step1Files = field(default_factory=Step1Files)
    is_processing: bool = False
    processing_message: str = ""
    auto_associate: bool = True
    process_mode: str = "copy"

    def copy(self) -> "Step1State":
        """返回包含独立 ``Step1Files`` 副本的状态快照。

        [EN] Return a state snapshot with an independent ``Step1Files`` copy.
        """
        return Step1State(
            selected_folder=self.selected_folder,
            files=self.files.copy(),
            is_processing=self.is_processing,
            processing_message=self.processing_message,
            auto_associate=self.auto_associate,
            process_mode=self.process_mode,
        )
