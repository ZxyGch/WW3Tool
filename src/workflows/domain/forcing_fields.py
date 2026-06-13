"""强迫场（forcing）选择与路径状态模型。

本模块属于 ``domain/`` 领域层，定义强迫场类型枚举及 Step 1 相关状态容器，
供无界面 CLI 与 Desktop 预处理流程共用，避免 UI 与业务逻辑耦合。

主要消费者：
- ``application/forcing_preparation.py``：强迫场准备用例
- ``application/forcing_inspection.py``：文件检测与自动关联
- ``desktop/view_models/forcing_step.py``：桌面端 Step 1 视图模型
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ForcingField(str, Enum):
    """WW3 强迫场类型枚举。

    成员值与 ``Step1Files`` 及 ``ForcingConfig`` 中的字段名一致。
    """

    WIND = "wind"
    CURRENT = "current"
    LEVEL = "level"
    ICE = "ice"


# 强迫场在 UI 与批处理中的固定展示/遍历顺序
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
        """
        return getattr(self, forcing_field.value)

    def set(self, forcing_field: ForcingField, path: Optional[str]) -> None:
        """按强迫场类型写入或清空路径。

        Args:
            forcing_field: 目标强迫场枚举值。
            path: 文件路径；``None`` 表示清除。
        """
        setattr(self, forcing_field.value, path)

    def clear(self, forcing_field: Optional[ForcingField] = None) -> None:
        """清除一个或全部强迫场路径。

        Args:
            forcing_field: 指定要清除的场类型；``None`` 时清空全部四类路径。
        """
        if forcing_field is None:
            for field_name in FORCING_FIELD_ORDER:
                self.set(field_name, None)
            return
        self.set(forcing_field, None)

    def copy(self) -> "Step1Files":
        """返回当前路径映射的浅拷贝。"""
        return Step1Files(wind=self.wind, current=self.current, level=self.level, ice=self.ice)

    def existing_items(self) -> list[tuple[ForcingField, str]]:
        """列出所有已配置（非空）的强迫场及其路径。

        Returns:
            ``(ForcingField, path)`` 元组列表，顺序遵循 ``FORCING_FIELD_ORDER``。
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
    """

    selected_folder: Optional[str] = None
    files: Step1Files = field(default_factory=Step1Files)
    is_processing: bool = False
    processing_message: str = ""
    auto_associate: bool = True
    process_mode: str = "copy"

    def copy(self) -> "Step1State":
        """返回包含独立 ``Step1Files`` 副本的状态快照。"""
        return Step1State(
            selected_folder=self.selected_folder,
            files=self.files.copy(),
            is_processing=self.is_processing,
            processing_message=self.processing_message,
            auto_associate=self.auto_associate,
            process_mode=self.process_mode,
        )
