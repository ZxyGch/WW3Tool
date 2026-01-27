"""
变量检测服务模块
负责检测 NetCDF 文件中的强迫场变量
"""
from netCDF4 import Dataset
from typing import Dict, List


class VariableDetector:
    """变量检测服务类"""
    
    @staticmethod
    def check_wind_variables(file_path: str) -> bool:
        """检查文件是否包含风场变量（接受 u10/v10 或 wndewd/wndnwd）"""
        try:
            with Dataset(file_path, "r") as ds:
                # 检查 u10 和 v10
                has_u10 = "u10" in ds.variables
                has_v10 = "v10" in ds.variables

                # 检查 wndewd 和 wndnwd（CFSR格式）
                has_wndewd = "wndewd" in ds.variables or "WNDEWD" in ds.variables
                has_wndnwd = "wndnwd" in ds.variables or "WNDNWD" in ds.variables

                # 检查 uwnd 和 vwnd
                has_uwnd = "uwnd" in ds.variables or "UWND" in ds.variables
                has_vwnd = "vwnd" in ds.variables or "VWND" in ds.variables

                # 如果包含任意一组变量，都认为是有效的风场文件
                return (has_u10 and has_v10) or (has_wndewd and has_wndnwd) or (has_uwnd and has_vwnd)
        except Exception:
            return False

    @staticmethod
    def check_current_variables(file_path: str) -> bool:
        """检查文件是否包含流场变量（只接受 uo 和 vo）"""
        try:
            with Dataset(file_path, "r") as ds:
                # 只检查 uo 和 vo
                has_uo = "uo" in ds.variables
                has_vo = "vo" in ds.variables

                return has_uo and has_vo
        except Exception:
            return False

    @staticmethod
    def check_level_variables(file_path: str) -> bool:
        """检查文件是否包含水位场变量（只接受 zos）"""
        try:
            with Dataset(file_path, "r") as ds:
                # 只检查 zos
                return "zos" in ds.variables
        except Exception:
            return False

    @staticmethod
    def check_ice_variables(file_path: str) -> bool:
        """检查文件是否包含海冰场变量（只接受 siconc）"""
        try:
            with Dataset(file_path, "r") as ds:
                # 只检查 siconc
                return "siconc" in ds.variables
        except Exception:
            return False

    @staticmethod
    def detect_forcing_fields(file_path: str) -> List[str]:
        """
        检测文件包含哪些强迫场
        
        返回包含的场名称列表，例如：['wind', 'current', 'level', 'ice']
        """
        fields = []
        try:
            with Dataset(file_path, "r") as ds:
                # 检查风场 (支持多种格式：u10/v10, wndewd/wndnwd, uwnd/vwnd)
                has_u10 = "u10" in ds.variables or "U10" in ds.variables
                has_v10 = "v10" in ds.variables or "V10" in ds.variables
                has_wndewd = "wndewd" in ds.variables or "WNDEWD" in ds.variables
                has_wndnwd = "wndnwd" in ds.variables or "WNDNWD" in ds.variables
                has_uwnd = "uwnd" in ds.variables or "UWND" in ds.variables
                has_vwnd = "vwnd" in ds.variables or "VWND" in ds.variables

                if (has_u10 and has_v10) or (has_wndewd and has_wndnwd) or (has_uwnd and has_vwnd):
                    fields.append("wind")

                # 检查流场 (uo/vo)
                has_uo = "uo" in ds.variables or "UO" in ds.variables
                has_vo = "vo" in ds.variables or "VO" in ds.variables
                if has_uo and has_vo:
                    fields.append("current")

                # 检查水位场 (zos)
                if "zos" in ds.variables or "ZOS" in ds.variables:
                    fields.append("level")

                # 检查海冰场 (siconc)
                if "siconc" in ds.variables or "SICONC" in ds.variables:
                    fields.append("ice")
        except Exception:
            pass

        return fields

    @staticmethod
    def detect_all_forcing_fields_in_file(file_path: str) -> Dict[str, bool]:
        """
        检测文件包含的所有强迫场变量（不处理文件，只检测）
        
        返回包含的场名称字典，例如：{'wind': True, 'current': True, 'level': True, 'ice': False}
        """
        detected = {}
        try:
            with Dataset(file_path, "r") as ds:
                # 检测风场
                has_u10 = "u10" in ds.variables
                has_v10 = "v10" in ds.variables
                has_wndewd = "wndewd" in ds.variables or "WNDEWD" in ds.variables
                has_wndnwd = "wndnwd" in ds.variables or "WNDNWD" in ds.variables
                has_uwnd = "uwnd" in ds.variables or "UWND" in ds.variables
                has_vwnd = "vwnd" in ds.variables or "VWND" in ds.variables
                detected['wind'] = (has_u10 and has_v10) or (has_wndewd and has_wndnwd) or (has_uwnd and has_vwnd)

                # 检测流场
                has_uo = "uo" in ds.variables
                has_vo = "vo" in ds.variables
                detected['current'] = has_uo and has_vo

                # 检测水位场
                detected['level'] = "zos" in ds.variables

                # 检测海冰场
                detected['ice'] = "siconc" in ds.variables
        except Exception:
            pass
        return detected
