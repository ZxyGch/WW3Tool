"""
Home 模块的全局状态管理和通用工具函数
用于在多个 mixin 类之间共享状态和UI创建逻辑
"""
import os
import platform
from PyQt6.QtWidgets import QVBoxLayout
from qfluentwidgets import HeaderCardWidget
from setting.language_manager import tr


class HomeState:
    """Home 模块的全局状态管理类"""
    
    # 网格类型状态
    _grid_type = None  # 存储翻译后的文本，如 "普通网格" 或 "Nested Grid"
    
    # 计算模式状态
    _calc_mode = None
    
    @classmethod
    def get_grid_type(cls, default=None):
        """获取当前网格类型
        
        Args:
            default: 如果未设置，返回的默认值。如果为 None 且未设置，返回 None
        
        Returns:
            网格类型字符串，如果未设置且 default 为 None，返回 None
        """
        if cls._grid_type is None:
            return default
        return cls._grid_type
    
    @classmethod
    def set_grid_type(cls, grid_type):
        """设置当前网格类型"""
        print("设置 grid_type：",grid_type)
        cls._grid_type = grid_type
    
    @classmethod
    def is_nested_grid(cls):
        """检查当前是否为嵌套网格"""
        # 如果未设置，默认返回 False（普通网格）
        grid_type = cls.get_grid_type(tr("step2_grid_type_normal", "普通网格"))
        nested_text = tr("step2_grid_type_nested", "嵌套网格")
        print("nested_text: ",nested_text,"grid_type: ",grid_type)

        return grid_type == nested_text
    
    @classmethod
    def get_calc_mode(cls, default=None):
        """获取当前计算模式"""
        if cls._calc_mode is None:
            return default
        return cls._calc_mode
    
    @classmethod
    def set_calc_mode(cls, calc_mode):
        """设置当前计算模式"""
        cls._calc_mode = calc_mode
    
    @classmethod
    def reset(cls):
        """重置所有状态"""
        cls._grid_type = None
        cls._calc_mode = None


def create_header_card(content_widget, title, include_vbox_style=False):
    """
    创建标准化的 HeaderCardWidget 卡片
    
    参数:
        content_widget: 父窗口部件
        title: 卡片标题
        include_vbox_style: 是否包含 QVBoxLayout 样式（第一步需要）
    
    返回:
        (card, card_layout): 返回卡片对象和内容布局对象
    """
    # 创建卡片
    card = HeaderCardWidget(content_widget)
    card.setTitle(title)
    
    # 构建样式字符串
    style = """
        HeaderCardWidget QLabel {
            font-weight: normal;
            margin-left: 0px;
            padding-left: 0px;
        }
    """
    
    # 第一步需要额外的 QVBoxLayout 样式
    if include_vbox_style:
        style += """
        HeaderCardWidget QVBoxLayout {
            margin: 3px;
            padding: 3px;
        }
        """
    
    card.setStyleSheet(style)
    
    # 设置标题内边距
    card.headerLayout.setContentsMargins(11, 10, 11, 12)
    
    # 创建内容布局
    card_layout = QVBoxLayout()
    card_layout.setSpacing(10)
    card_layout.setContentsMargins(0, 0, 0, 0)
    
    return card, card_layout
