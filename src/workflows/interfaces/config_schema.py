"""params.yml 的字段说明，供程序自省。

模板里的注释是给人读的，而且有些结构从注释里看不出来——例如
``grid_type: normal`` 的 dx/dy 其实取自 ``structured.nested.levels[0]``，
一个名字里带 nested 的地方。调用方不该为了配置这个工具去读源码。

[EN] Machine-readable description of params.yml, so a caller does not have to
read the source to find out where a setting lives.
"""

from __future__ import annotations

from typing import Any

from ..domain.parameter_catalog import (
    COASTLINE_PRECISION_OPTIONS,
    FILE_SPLIT_OPTIONS,
    SMC_BATHYMETRY_OPTIONS,
    STRUCTURED_BATHYMETRY_OPTIONS,
)

__all__ = ["build_schema"]


def _f(path, type_, desc, *, options=None, default=None, required=False, note=None):
    entry: dict[str, Any] = {"path": path, "type": type_, "description": desc}
    if options is not None:
        entry["options"] = list(options)
    if default is not None:
        entry["default"] = default
    if required:
        entry["required"] = True
    if note:
        entry["note"] = note
    return entry


def build_schema() -> dict[str, Any]:
    """描述 params.yml 里可配置的字段。"""
    return {
        "version": 1,
        "files": {
            "global": {
                "path": "~/.config/ww3tool/params.yml (macOS: ~/Library/Application Support/ww3tool/params.yml)",
                "description": "全局设置：服务器、可执行路径、参考数据位置。pip 升级不会覆盖。",
                "env_override": "WW3TOOL_PARAMS",
            },
            "workdir": {
                "path": "<workdir>/params.yml",
                "description": "单次算例的参数，由 `ww3tool workdir <path>` 创建。",
            },
        },
        "fields": [
            _f("workdir.path", "path", "本次算例的工作目录"),
            _f("grid.mesh_type", "enum", "网格类型",
               options=["structured", "smc", "unstructured"], default="structured"),
            _f("grid.grid_type", "enum", "单域还是嵌套", options=["normal", "nested"],
               default="normal"),
            _f("grid.lon", "list[float]", "经度范围 [west, east]", required=True,
               note="可写 -180~180 或 0~360；跨日界线时 east 可大于 180（如 150~210）。"
                    "整圈（跨度 360）且纬度 -90~90 时按全球网格处理，自动置 IS_GLOBAL 并去掉重复经线。"),
            _f("grid.lat", "list[float]", "纬度范围 [south, north]", required=True),
            _f("grid.reference_data_path", "path",
               "地形与岸线数据目录（gebco.nc / etopo*.nc / coastal_bound_*.mat）",
               required=True),
            _f("grid.structured.nested.levels[0].dx", "float", "经度分辨率（度）",
               required=True,
               note="grid_type=normal 时分辨率也取自这里——虽然键名里带 nested。"
                    "levels[0] 的 lon/lat 会被顶层 grid.lon / grid.lat 覆盖。"),
            _f("grid.structured.nested.levels[0].dy", "float", "纬度分辨率（度）",
               required=True),
            _f("grid.structured.bathymetry", "enum", "地形数据源",
               options=STRUCTURED_BATHYMETRY_OPTIONS, default="GEBCO",
               note="全球或很宽的域慎用 GEBCO：底图窗口一次性整片读入，"
                    "全球约 7 GiB，与目标分辨率无关。"),
            _f("grid.structured.coastline_precision", "enum", "岸线精度档",
               options=COASTLINE_PRECISION_OPTIONS, default="full",
               note="常驻内存 low≈92MB / inter≈198MB / high≈558MB / full≈956MB。"),
            _f("grid.structured.split_lim", "float", "大多边形切分尺度（度）",
               default=0,
               note="0 表示几乎每个多边形都切，全球域下极慢；建议取 5*max(dx,dy) 量级。"),
            _f("grid.structured.min_dist", "float", "多边形与边界的最小距离阈值", default=20),
            _f("grid.structured.cut_off", "float", "陆海分界深度", default=0),
            _f("grid.structured.lim_bathy", "float", "格子判为湿所需的底图湿点比例", default=0.4),
            _f("grid.structured.lim_val", "float", "格子被岸线判干的覆盖比例", default=0.5),
            _f("grid.structured.lake_tol", "int", "小于此格数的水体填掉；负数表示只留最大水体",
               default=50),
            _f("forcing.wind", "path", "风场 NetCDF"),
            _f("forcing.current", "path", "流场 NetCDF"),
            _f("forcing.level", "path", "水位 NetCDF"),
            _f("forcing.ice", "path", "海冰 NetCDF"),
            _f("presets.file_split", "enum", "强迫场输出切分粒度",
               options=FILE_SPLIT_OPTIONS),
            _f("grid.smc.bathymetry", "enum", "SMC 网格地形源",
               options=SMC_BATHYMETRY_OPTIONS),
            _f("server.ssh_config_host", "str", "~/.ssh/config 里的主机别名"),
            _f("server.host", "str", "服务器地址（不用 ssh_config 时）"),
            _f("server.user", "str", "登录用户名"),
            _f("server.default_remote_dir", "path", "远端工作目录"),
        ],
        "environment": [
            {"name": "WW3TOOL_PARAMS", "description": "指定全局配置文件位置"},
            {"name": "WW3TOOL_ROOT", "description": "指定资源根目录"},
            {"name": "WW3TOOL_MESHGEN_WORKERS", "description": "网格生成的进程数上限"},
            {"name": "WW3TOOL_MESHGEN_MEM_MB", "description": "覆盖内存预算（MiB）"},
            {"name": "WW3TOOL_MESHGEN_MEM_ABORT_FRACTION",
             "description": "内存看门狗的中止阈值，默认 0.9"},
            {"name": "WW3TOOL_FORCE_DESKTOP", "description": "无图形环境下仍强制启动桌面端"},
        ],
    }
