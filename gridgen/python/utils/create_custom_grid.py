"""
Create Custom Grid Script

生成一个宽10度、长50度的网格，水深统一无限深，
全部为水域，无任何陆地。
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
    """
    
    # 网格参数设置
    # 假设网格从经度0到50度，纬度0到10度
    # 宽10度（纬度），长50度（经度）
    lon_range = [-140, -132]  # 经度范围：长50度
    lat_range = [-40, -39.5]  # 纬度范围：宽10度
    
    # 网格分辨率（可以根据需要调整）
    dx = 0.05  # 经度分辨率
    dy = 0.05  # 纬度分辨率
    
    # 自动处理范围顺序（确保从小到大）
    lon_min, lon_max = min(lon_range), max(lon_range)
    lat_min, lat_max = min(lat_range), max(lat_range)
    
    # 创建输出目录
    script_path = os.path.abspath(__file__)
    base_dir = os.path.dirname(script_path)
    project_root = os.path.dirname(base_dir) if os.path.basename(base_dir) == 'python' else base_dir
    # 如果全局 OUT_DIR 已设置，则使用该目录；否则使用默认 result 目录
    out_dir = OUT_DIR if OUT_DIR else os.path.join(project_root, 'result')
    os.makedirs(out_dir, exist_ok=True)
    
    # 创建网格坐标
    print("=" * 70)
    print("创建自定义网格")
    print("=" * 70)
    print(f"输入范围: 经度 {lon_range}, 纬度 {lat_range}")
    print(f"实际范围: 经度 [{lon_min}, {lon_max}], 纬度 [{lat_min}, {lat_max}]")
    print(f"分辨率: {dx} x {dy} 度")
    print("=" * 70)
    
    # 计算网格点数（使用绝对值确保为正数）
    nx = int(round(abs(lon_max - lon_min) / dx)) + 1
    ny = int(round(abs(lat_max - lat_min) / dy)) + 1
    
    lon1d = np.linspace(lon_min, lon_max, nx)
    lat1d = np.linspace(lat_min, lat_max, ny)
    lon, lat = np.meshgrid(lon1d, lat1d)
    
    print(f"网格大小: {nx} x {ny} 点")
    
    # 创建无限深的水深数据（所有水域都是-10000米）
    depth = np.full_like(lon, -10000.0, dtype=np.float64)
    
    # 创建初始陆地-海洋掩膜（全部为水域，无陆地）
    # WAVEWATCH III约定：0=陆地，1=水域，2=边界点，3=排除点
    mask = np.ones_like(depth, dtype=np.int32)
    
    # 验证：确保所有点都是水域（值为1），没有任何陆地（值为0）
    assert np.all(mask == 1), "错误：掩膜中不应包含非水域点！"
    assert np.sum(mask == 0) == 0, "错误：掩膜中不应包含陆地点！"
    
    print(f"水域点数: {np.sum(mask == 1)}")
    print(f"陆地点数: {np.sum(mask == 0)}")
    print(f"✓ 验证通过：所有 {mask.size} 个网格点都是水域（无陆地）")
    
    # 创建obstruction grids（无陆地边界，全部为零）
    print("\n创建obstruction grids...")
    print("无陆地边界，创建全零obstruction grids...")
    sx1 = np.zeros_like(mask, dtype=np.float64)
    sy1 = np.zeros_like(mask, dtype=np.float64)
    
    # 写入输出文件
    print("\n写入输出文件...")
    depth_scale = 1000
    obstr_scale = 100
    
    # 写入水深文件
    d = np.round(depth * depth_scale).astype(int)
    fname = 'grid'
    write_ww3file(os.path.join(out_dir, f"{fname}.bot"), d)
    print(f"  已写入: {fname}.bot")
    
    # 写入掩膜文件
    # 在写入前再次验证：确保mask全为1（水域）
    assert np.all(mask == 1), "错误：写入前验证失败，掩膜包含非水域点！"
    write_ww3file(os.path.join(out_dir, f"{fname}.nobound_mask"), mask)
    print(f"  已写入: {fname}.nobound_mask (全部为水域，无陆地)")
    
    # 写入obstruction文件
    d1 = np.round(sx1 * obstr_scale).astype(int)
    d2 = np.round(sy1 * obstr_scale).astype(int)
    write_ww3obstr(os.path.join(out_dir, f"{fname}.obst"), d1, d2)
    print(f"  已写入: {fname}.obst")
    
    # 写入metadata文件
    # 使用相对路径（只使用文件名），这样 WAVEWATCH 可以在任何目录运行
    # 如果文件在同一目录，WAVEWATCH 会自动找到它们
    meta_prefix = os.path.join(out_dir, fname)
    # Use actual grid point spacing (calculated from lon/lat arrays) to ensure
    # grid.meta dx/dy matches the actual grid.bot file structure
    write_ww3meta(meta_prefix, None, 'RECT', lon, lat,
                  1.0 / depth_scale, 1.0 / obstr_scale, 1.0)
    
    # 修复 meta 文件中的路径：将绝对路径改为相对路径（只使用文件名）
    meta_file = os.path.join(out_dir, f"{fname}.meta")
    if os.path.exists(meta_file):
        with open(meta_file, 'r', encoding='utf-8') as f:
            content = f.read()
        # 替换绝对路径为相对路径（只保留文件名）
        import re
        # 匹配 '绝对路径/文件名.扩展名' 格式，替换为 '文件名.扩展名'
        pattern = r"'([^']*)/([^'/]+\.(?:bot|obst|nobound_mask))'"
        content = re.sub(pattern, r"'\2'", content)
        with open(meta_file, 'w', encoding='utf-8') as f:
            f.write(content)
    print(f"  已写入: {fname}.meta")
    
    # 最终验证
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
