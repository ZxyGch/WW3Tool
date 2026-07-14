"""
Create Custom Grid Script

生成一个宽10度、长50度的网格，水深统一无限深，
全部为水域，无任何陆地。

[EN] Generate a grid 10 degrees wide (latitude) and 50 degrees long
(longitude), with uniform infinite depth (-10000 m), entirely water and no
land.
"""

import os
import sys
import numpy as np

# Add parent directory to path
script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

# Import modules using direct file imports to avoid conflicts with stdlib 'io'
import importlib.util

# 全局输出目录（可在外部修改），为 None 时使用默认 result 目录
# [EN] Global output directory (can be overridden externally); if None, use the default result directory.
OUT_DIR = "/Users/zxy/ocean/WW3Tool/workSpace/momo"

# Load grid.create_obstr
grid_obstr_path = os.path.join(script_dir, 'grid', 'create_obstr.py')
spec = importlib.util.spec_from_file_location("create_obstr", grid_obstr_path)
create_obstr_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(create_obstr_module)
create_obstr = create_obstr_module.create_obstr

# Load io.write_ww3file
io_file_path = os.path.join(script_dir, 'io', 'write_ww3file.py')
spec = importlib.util.spec_from_file_location("write_ww3file", io_file_path)
write_ww3file_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(write_ww3file_module)
write_ww3file = write_ww3file_module.write_ww3file

# Load io.write_ww3obstr
io_obstr_path = os.path.join(script_dir, 'io', 'write_ww3obstr.py')
spec = importlib.util.spec_from_file_location("write_ww3obstr", io_obstr_path)
write_ww3obstr_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(write_ww3obstr_module)
write_ww3obstr = write_ww3obstr_module.write_ww3obstr

# Load io.write_ww3meta - patch the import before loading
io_dir = os.path.join(script_dir, 'io')
io_meta_path = os.path.join(io_dir, 'write_ww3meta.py')

# Read the file and patch the import
with open(io_meta_path, 'r', encoding='utf-8') as f:
    meta_code = f.read()

# Replace relative import with absolute import
meta_code = meta_code.replace('from .read_namelist import read_namelist', 
                              'from io.read_namelist import read_namelist')

# Create a temporary module
import types
write_ww3meta_module = types.ModuleType('io.write_ww3meta')
write_ww3meta_module.__file__ = io_meta_path
write_ww3meta_module.__package__ = 'io'

# Add io directory to path
if io_dir not in sys.path:
    sys.path.insert(0, io_dir)

# Execute the patched code
exec(compile(meta_code, io_meta_path, 'exec'), write_ww3meta_module.__dict__)
write_ww3meta = write_ww3meta_module.write_ww3meta


def create_custom_grid():
    """
    创建自定义网格：
    - 宽10度（纬度方向），长50度（经度方向）
    - 水深统一无限深（-10000米）
    - 全部为水域，无任何陆地

    [EN] Create a custom grid:
    - 10 degrees wide in latitude, 50 degrees long in longitude.
    - Uniform infinite depth (-10000 m).
    - Entirely water cells, no land.
    """
    
    # 网格参数设置
    # [EN] Grid parameter settings.
    # 假设网格从经度0到50度，纬度0到10度
    # [EN] Assume the grid spans longitude 0 to 50 deg and latitude 0 to 10 deg.
    # 宽10度（纬度），长50度（经度）
    # [EN] 10 deg wide (latitude), 50 deg long (longitude).
    lon_range = [-140, -132]  # 经度范围：长50度
    # [EN] Longitude range: 50 deg long.
    lat_range = [-40, -39.5]  # 纬度范围：宽10度
    # [EN] Latitude range: 10 deg wide.

    # 网格分辨率（可以根据需要调整）
    # [EN] Grid resolution (adjustable as needed).
    dx = 0.05  # 经度分辨率
    # [EN] Longitude resolution.
    dy = 0.05  # 纬度分辨率
    # [EN] Latitude resolution.

    # 自动处理范围顺序（确保从小到大）
    # [EN] Auto-sort range limits (ensure ascending order).
    lon_min, lon_max = min(lon_range), max(lon_range)
    lat_min, lat_max = min(lat_range), max(lat_range)
    
    # 创建输出目录
    # [EN] Create the output directory.
    script_path = os.path.abspath(__file__)
    base_dir = os.path.dirname(script_path)
    project_root = os.path.dirname(base_dir) if os.path.basename(base_dir) == 'python' else base_dir
    # 如果全局 OUT_DIR 已设置，则使用该目录；否则使用默认 result 目录
    # [EN] Use the global OUT_DIR if set; otherwise fall back to the default result directory.
    out_dir = OUT_DIR if OUT_DIR else os.path.join(project_root, 'result')
    os.makedirs(out_dir, exist_ok=True)

    # 创建网格坐标
    # [EN] Create grid coordinates.
    print("=" * 70)
    print("创建自定义网格")
    print("=" * 70)
    print(f"输入范围: 经度 {lon_range}, 纬度 {lat_range}")
    print(f"实际范围: 经度 [{lon_min}, {lon_max}], 纬度 [{lat_min}, {lat_max}]")
    print(f"分辨率: {dx} x {dy} 度")
    print("=" * 70)

    # 计算网格点数（使用绝对值确保为正数）
    # [EN] Compute the number of grid points (use absolute values to ensure positivity).
    nx = int(round(abs(lon_max - lon_min) / dx)) + 1
    ny = int(round(abs(lat_max - lat_min) / dy)) + 1
    
    lon1d = np.linspace(lon_min, lon_max, nx)
    lat1d = np.linspace(lat_min, lat_max, ny)
    lon, lat = np.meshgrid(lon1d, lat1d)
    
    print(f"网格大小: {nx} x {ny} 点")
    
    # 创建无限深的水深数据（所有水域都是-10000米）
    # [EN] Create bathymetry with infinite depth (all water cells are -10000 m).
    depth = np.full_like(lon, -10000.0, dtype=np.float64)

    # 创建初始陆地-海洋掩膜（全部为水域，无陆地）
    # [EN] Create the initial land-sea mask (all water, no land).
    # WAVEWATCH III约定：0=陆地，1=水域，2=边界点，3=排除点
    # [EN] WW3 convention: 0 = land, 1 = water, 2 = boundary point, 3 = excluded point.
    mask = np.ones_like(depth, dtype=np.int32)

    # 验证：确保所有点都是水域（值为1），没有任何陆地（值为0）
    # [EN] Verify that all points are water (value 1) and no land (value 0) exists.
    assert np.all(mask == 1), "错误：掩膜中不应包含非水域点！"
    assert np.sum(mask == 0) == 0, "错误：掩膜中不应包含陆地点！"

    print(f"水域点数: {np.sum(mask == 1)}")
    print(f"陆地点数: {np.sum(mask == 0)}")
    print(f"✓ 验证通过：所有 {mask.size} 个网格点都是水域（无陆地）")

    # 创建obstruction grids（无陆地边界，全部为零）
    # [EN] Create obstruction grids (no land boundaries, all zeros).
    print("\n创建obstruction grids...")
    print("无陆地边界，创建全零obstruction grids...")
    sx1 = np.zeros_like(mask, dtype=np.float64)
    sy1 = np.zeros_like(mask, dtype=np.float64)
    
    # 写入输出文件
    # [EN] Write output files.
    print("\n写入输出文件...")
    depth_scale = 1000
    obstr_scale = 100

    # 写入水深文件
    # [EN] Write bathymetry file.
    d = np.round(depth * depth_scale).astype(int)
    fname = 'grid'
    write_ww3file(os.path.join(out_dir, f"{fname}.bot"), d)
    print(f"  已写入: {fname}.bot")

    # 写入掩膜文件
    # [EN] Write mask file.
    # 在写入前再次验证：确保mask全为1（水域）
    # [EN] Re-verify before writing: ensure the mask is all 1 (water).
    assert np.all(mask == 1), "错误：写入前验证失败，掩膜包含非水域点！"
    write_ww3file(os.path.join(out_dir, f"{fname}.nobound_mask"), mask)
    print(f"  已写入: {fname}.nobound_mask (全部为水域，无陆地)")

    # 写入obstruction文件
    # [EN] Write obstruction file.
    d1 = np.round(sx1 * obstr_scale).astype(int)
    d2 = np.round(sy1 * obstr_scale).astype(int)
    write_ww3obstr(os.path.join(out_dir, f"{fname}.obst"), d1, d2)
    print(f"  已写入: {fname}.obst")
    
    meta_prefix = os.path.join(out_dir, fname)
    write_ww3meta(meta_prefix, None, 'RECT', lon, lat,
                  1.0 / depth_scale, 1.0 / obstr_scale, 1.0)
    meta_file = os.path.join(out_dir, "grid.nml")
    if os.path.exists(meta_file):
        with open(meta_file, 'r', encoding='utf-8') as f:
            content = f.read()
        import re
        pattern = r"'([^']*)/([^'/]+\.(?:bot|obst|nobound_mask|mask_nobound))'"
        content = re.sub(pattern, r"'\2'", content)
        with open(meta_file, 'w', encoding='utf-8') as f:
            f.write(content)
    print("  已写入: grid.nml")
    
    # 最终验证
    # [EN] Final verification.
    print("\n" + "=" * 70)
    print("最终验证")
    print("=" * 70)
    total_points = nx * ny
    water_points = np.sum(mask == 1)
    land_points = np.sum(mask == 0)

    if land_points == 0 and water_points == total_points:
        print(f"✓ 验证通过：网格完全由水域组成，无任何陆地")
        print(f"  - 总网格点数: {total_points}")
        print(f"  - 水域点数: {water_points} (100%)")
        print(f"  - 陆地点数: {land_points} (0%)")
    else:
        print(f"⚠ 警告：网格包含陆地！")
        print(f"  - 总网格点数: {total_points}")
        print(f"  - 水域点数: {water_points}")
        print(f"  - 陆地点数: {land_points}")

    # 统计信息
    # [EN] Summary statistics.
    print("\n" + "=" * 70)
    print("网格生成完成！")
    print("=" * 70)
    print(f"输出目录: {out_dir}")
    print(f"总网格点数: {total_points}")
    print(f"水域点数: {water_points}")
    print(f"陆地点数: {land_points}")
    print(f"水深范围: {np.min(depth):.1f} 到 {np.max(depth):.1f} 米")
    print("=" * 70)


if __name__ == '__main__':
    create_custom_grid()
