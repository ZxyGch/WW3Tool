"""WW3 Step 1 强迫场文件路径与命名管理。

[EN] WW3 Step 1 forcing field file path and naming management.

WW3 工作流第一步要求将风/流/水位/海冰 NetCDF 放入工作目录，并按照约定命名
（如 ``wind.nc``、``wind_current_level_ice.nc``）。本模块负责：

[EN] The first step of the WW3 workflow requires placing wind/current/level/ice NetCDF
files into the working directory with conventional naming (e.g. ``wind.nc``,
``wind_current_level_ice.nc``). This module is responsible for:

- 根据已选场类型生成目标文件名；
- 从已有文件名反推包含的场；
- 在桌面端将检测到的路径同步到 UI 按钮（``set_file_path``）。

[EN] - Generating target filenames based on selected field types;
- Reverse-engineering included fields from existing filenames;
- Syncing detected paths to UI buttons on the desktop side (``set_file_path``).
"""
import os
from typing import List, Optional
from ...support.translations import tr


class FilePathManager:
    """强迫场文件命名与 UI 路径绑定的静态工具类。

    [EN] Static utility class for forcing file naming and UI path binding.

    所有方法均为 ``@staticmethod``，不持有状态；供 ``FileService`` 与
    ``ImportForcingFileUseCase`` 等在 Step 1 导入流程中调用。

    [EN] All methods are ``@staticmethod`` and stateless; intended for use by
    ``FileService`` and ``ImportForcingFileUseCase`` during the Step 1 import workflow.
    """
    
    @staticmethod
    def generate_forcing_filename(fields: List[str], auto_associate: bool = True) -> str:
        """
        根据包含的强迫场生成文件名

        [EN] Generate a filename based on the included forcing fields.
        
        参数:
            fields: 包含的场名称列表，例如：['wind', 'current', 'level', 'ice']
            auto_associate: 是否自动关联场，如果为 False 且只有一个场，只使用该场的名称

        [EN] Parameters:
            fields: List of included field names, e.g. ['wind', 'current', 'level', 'ice']
            auto_associate: Whether to auto-associate fields. If False and only one field, use only that field's name.
        
        返回:
            文件名，例如：'wind_current_level_ice.nc' 或 'wind.nc'

        [EN] Returns:
            Filename, e.g. 'wind_current_level_ice.nc' or 'wind.nc'
        """
        if not fields:
            return "forcing.nc"

        # 如果自动关联关闭且只有一个场，只使用该场的名称
        # [EN] If auto-associate is off and there is only one field, use only that field's name
        if not auto_associate and len(fields) == 1:
            return f"{fields[0]}.nc"

        # 按照固定的顺序排列：wind, current, level, ice
        # [EN] Arrange in a fixed order: wind, current, level, ice
        field_order = ["wind", "current", "level", "ice"]
        ordered_fields = [f for f in field_order if f in fields]

        # 如果顺序中没有的，添加到末尾
        # [EN] Fields not in the predefined order are appended at the end
        for f in fields:
            if f not in ordered_fields:
                ordered_fields.append(f)

        filename = "_".join(ordered_fields) + ".nc"
        return filename

    @staticmethod
    def parse_forcing_filename(filename: str) -> List[str]:
        """
        解析强迫场文件名，提取包含的场

        [EN] Parse a forcing filename and extract the included fields.
        
        参数:
            filename: 文件名，例如：'wind_current_level_ice.nc' 或 'wind.nc'

        [EN] Parameters:
            filename: Filename, e.g. 'wind_current_level_ice.nc' or 'wind.nc'
        
        返回:
            包含的场名称列表，例如：['wind', 'current', 'level', 'ice'] 或 ['wind']

        [EN] Returns:
            List of included field names, e.g. ['wind', 'current', 'level', 'ice'] or ['wind']
        """
        if not filename or not filename.endswith('.nc'):
            return []

        # 移除扩展名
        # [EN] Remove the file extension
        name_without_ext = filename[:-3]

        # 按照固定的顺序排列的字段名
        # [EN] Field names in a fixed order
        field_names = ["wind", "current", "level", "ice"]

        # 分割文件名并提取匹配的场名
        # [EN] Split the filename and extract matching field names
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

        [EN] Set the forcing file path for the specified field type and update the button text.
        
        参数:
            instance: 主窗口实例（需要包含 log 方法和按钮属性）
            field_type: 场类型 ('wind', 'current', 'level', 'ice')
            file_path: 文件路径
            filename: 文件名（用于显示在按钮上）

        [EN] Parameters:
            instance: Main window instance (requires log method and button attributes)
            field_type: Field type ('wind', 'current', 'level', 'ice')
            file_path: File path
            filename: Filename (for display on the button)
        """
        # 设置文件路径属性
        # [EN] Set the file path attribute
        attr_name = f'selected_{field_type}_file' if field_type != 'wind' else 'selected_origin_file'
        if not hasattr(instance, attr_name):
            setattr(instance, attr_name, None)
        setattr(instance, attr_name, file_path)

        # 更新按钮文本
        # [EN] Update button text
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
        # [EN] Log the result
        log_messages = {
            'wind': tr("log_auto_fill_wind", "✅ 检测到风场变量（u10/v10），已自动填充风场"),
            'current': tr("log_auto_fill_current", "✅ 检测到流场变量（uo/vo），已自动填充流场"),
            'level': tr("log_auto_fill_level", "✅ 检测到水位场变量 'zos'，已自动填充水位场"),
            'ice': tr("log_auto_fill_ice", "✅ 检测到海冰场变量 'siconc'，已自动填充海冰场")
        }
        
        if hasattr(instance, 'log'):
            instance.log(log_messages.get(field_type, ""))
