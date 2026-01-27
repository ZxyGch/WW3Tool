"""
文件路径管理模块
负责处理强迫场文件的路径和文件名
"""
import os
from typing import List, Optional
from setting.language_manager import tr


class FilePathManager:
    """文件路径管理服务类"""
    
    @staticmethod
    def generate_forcing_filename(fields: List[str], auto_associate: bool = True) -> str:
        """
        根据包含的强迫场生成文件名
        
        参数:
            fields: 包含的场名称列表，例如：['wind', 'current', 'level', 'ice']
            auto_associate: 是否自动关联场，如果为 False 且只有一个场，只使用该场的名称
        
        返回:
            文件名，例如：'wind_current_level_ice.nc' 或 'wind.nc'
        """
        if not fields:
            return "forcing.nc"

        # 如果自动关联关闭且只有一个场，只使用该场的名称
        if not auto_associate and len(fields) == 1:
            return f"{fields[0]}.nc"

        # 按照固定的顺序排列：wind, current, level, ice
        field_order = ["wind", "current", "level", "ice"]
        ordered_fields = [f for f in field_order if f in fields]

        # 如果顺序中没有的，添加到末尾
        for f in fields:
            if f not in ordered_fields:
                ordered_fields.append(f)

        filename = "_".join(ordered_fields) + ".nc"
        return filename

    @staticmethod
    def parse_forcing_filename(filename: str) -> List[str]:
        """
        解析强迫场文件名，提取包含的场
        
        参数:
            filename: 文件名，例如：'wind_current_level_ice.nc' 或 'wind.nc'
        
        返回:
            包含的场名称列表，例如：['wind', 'current', 'level', 'ice'] 或 ['wind']
        """
        if not filename or not filename.endswith('.nc'):
            return []

        # 移除扩展名
        name_without_ext = filename[:-3]

        # 按照固定的顺序排列的字段名
        field_names = ["wind", "current", "level", "ice"]

        # 分割文件名并提取匹配的场名
        parts = name_without_ext.split('_')
        fields = []

        for field in field_names:
            if field in parts:
                fields.append(field)

        return fields

    @staticmethod
    def set_file_path(instance, field_type: str, file_path: str, filename: str):
        """
        设置指定类型的强迫场文件路径并更新按钮文本
        
        参数:
            instance: 主窗口实例（需要包含 log 方法和按钮属性）
            field_type: 场类型 ('wind', 'current', 'level', 'ice')
            file_path: 文件路径
            filename: 文件名（用于显示在按钮上）
        """
        # 设置文件路径属性
        attr_name = f'selected_{field_type}_file' if field_type != 'wind' else 'selected_origin_file'
        if not hasattr(instance, attr_name):
            setattr(instance, attr_name, None)
        setattr(instance, attr_name, file_path)

        # 更新按钮文本
        button_attr_map = {
            'wind': 'btn_choose_wind_file',
            'current': 'btn_choose_current_file',
            'level': 'btn_choose_level_file',
            'ice': 'btn_choose_ice_file_home'
        }
        
        button_attr = button_attr_map.get(field_type)
        if button_attr and hasattr(instance, button_attr):
            button = getattr(instance, button_attr)
            file_name = filename if len(filename) <= 30 else filename[:27] + "..."
            if hasattr(instance, '_set_home_forcing_button_text'):
                instance._set_home_forcing_button_text(button, file_name, filled=True)
            else:
                button.setText(file_name)

        # 记录日志
        log_messages = {
            'wind': tr("log_auto_fill_wind", "✅ 检测到风场变量（u10/v10），已自动填充风场"),
            'current': tr("log_auto_fill_current", "✅ 检测到流场变量（uo/vo），已自动填充流场"),
            'level': tr("log_auto_fill_level", "✅ 检测到水位场变量 'zos'，已自动填充水位场"),
            'ice': tr("log_auto_fill_ice", "✅ 检测到海冰场变量 'siconc'，已自动填充海冰场")
        }
        
        if hasattr(instance, 'log'):
            instance.log(log_messages.get(field_type, ""))
