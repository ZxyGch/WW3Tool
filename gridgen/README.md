# WAVEWATCH III Grid Generator

WAVEWATCH III 网格生成工具（Python 版本）。

## 目录

- [概述](#概述)
- [系统要求](#系统要求)
- [安装](#安装)
- [快速开始](#快速开始)
- [参数说明](#参数说明)
- [输出文件](#输出文件)
- [常见问题](#常见问题)
- [性能优化](#性能优化)

## 概述

Grid Generator 是 WAVEWATCH III 波浪模型的网格生成工具，用于创建包含以下信息的网格文件：

- **Bathymetry（水深）**：从高分辨率全球水深数据集（GEBCO、ETOPO1、ETOPO2）生成
- **Land-Sea Mask（陆海掩膜）**：基于 GSHHS 海岸线数据生成
- **Obstruction Grids（障碍物网格）**：计算海岸线对波浪传播的阻碍效应

### 主要功能

1. **网格坐标定义**：生成规则或曲线网格坐标
2. **水深数据生成**：从全球水深数据集插值/平均生成网格水深
3. **边界处理**：使用 GSHHS 海岸线数据识别和处理陆地边界
4. **掩膜清理**：使用边界多边形清理初始陆海掩膜
5. **障碍物计算**：计算 x 和 y 方向的波浪传播障碍物

## 系统要求

- Python 3.7 或更高版本（推荐 3.9+）
- 必需的 Python 包：
  ```
  numpy >= 1.19.0
  scipy >= 1.5.0
  netCDF4 >= 1.5.0
  matplotlib >= 3.3.0
  ```

## 安装

### 1. 下载参考数据

在开始使用之前，需要下载必要的参考数据（水深数据和海岸线边界数据）。

**方法一：使用脚本自动下载（推荐）**

```bash
cd gridgen
chmod +x get_reference_data.sh
./get_reference_data.sh
```

该脚本会自动：
- 从 NOAA 下载 GSHHS 海岸线边界数据（`gridgen_addit.tar.gz`）
- 从 CEDA 下载 GEBCO 2025 水深数据（`gebco_2025_sub_ice_topo.zip`）
- 解压到 `reference_data` 目录

**方法二：手动下载**

如果自动下载失败，可以手动下载：

1. **GSHHS 边界数据**：
   - 下载地址：`ftp://polar.ncep.noaa.gov/waves/gridgen/gridgen_addit.tar.gz`
   - 解压到 `gridgen/reference_data/` 目录

2. **GEBCO 水深数据**：
   - 下载地址：`https://dap.ceda.ac.uk/bodc/gebco/global/gebco_2025/sub_ice_topography_bathymetry/netcdf/gebco_2025_sub_ice_topo.zip`
   - 解压到 `gridgen/reference_data/` 目录
   - 确保解压后的文件名为 `gebco.nc`

**注意**：
- 确保 `reference_data` 目录存在，如果不存在请先创建：`mkdir -p gridgen/reference_data`
- GEBCO 数据文件较大（约 10GB），下载可能需要较长时间
- 如果网络不稳定，建议使用下载工具（如 `wget` 或 `curl`）的断点续传功能

### 2. 安装软件依赖


```bash
pip install numpy scipy netcdf4 matplotlib
```

## 快速开始

### 使用方式

直接调用函数，通过参数传递配置，简单易用，无需配置文件。

### 基本用法

```python
import sys
sys.path.append('/path/to/gridgen')
from python.create_grid import create_grid

# 基本用法（直接调用函数）
create_grid(
    dx=0.05,
    dy=0.05,
    lon_range=[110, 130],
    lat_range=[10, 30],
    out_dir='./output'
)

# 使用自定义参数
create_grid(
    dx=0.05,
    dy=0.05,
    lon_range=[110, 130],
    lat_range=[10, 30],
    ref_grid='gebco',
    boundary='full',
    out_dir='./output'
)
```

**注意**：
- 确保已正确设置 Python 路径，指向 `gridgen` 目录
- 默认参考数据目录为 `gridgen/reference_data/`，输出目录为 `gridgen/result/`
- 可以通过 `ref_dir` 和 `out_dir` 参数自定义路径

## 参数说明

### 必需参数

| 参数 | 类型 | 说明 | 默认值 |
|------|------|------|--------|
| `dx` | float | 经度方向网格分辨率（度） | 0.05 |
| `dy` | float | 纬度方向网格分辨率（度） | 0.05 |
| `lon_range` | list | 经度范围 [west, east] | [110, 130] |
| `lat_range` | list | 纬度范围 [south, north] | [10, 30] |

### 可选参数

#### 输入/输出路径

| 参数 | 类型 | 说明 | 默认值 |
|------|------|------|--------|
| `bin_dir` | str | Bin 目录路径 | `../bin/` |
| `ref_dir` | str | 参考数据目录路径 | `../reference_data/` |
| `out_dir` | str | 输出目录路径 | `../result/` |
| `fname` | str | 输出文件名前缀 | `grid` |

#### 水深数据

| 参数 | 类型 | 说明 | 默认值 |
|------|------|------|--------|
| `ref_grid` | str | 水深数据源 (`gebco`, `etopo1`, `etopo2`) | `gebco` |
| `LIM_BATHY` | float | 单元格必须为湿地的比例阈值 | 0.1 |
| `CUT_OFF` | float | 区分干湿单元格的深度阈值（米） | 0.1 |
| `DRY_VAL` | float | 干单元格的深度值 | 999999 |

#### 边界数据

| 参数 | 类型 | 说明 | 默认值 |
|------|------|------|--------|
| `boundary` | str | GSHHS 边界级别 (`full`, `high`, `inter`, `low`, `coarse`) | `full` |
| `read_boundary` | int | 是否读取边界数据 (0/1) | 1 |
| `opt_poly` | int | 是否使用可选多边形 (0/1) | 0 |
| `fname_poly` | str | 可选多边形文件名 | `user_polygons.flag` |
| `LIM_VAL` | float | 多边形掩膜的比例阈值 | 0.5 |
| `OFFSET` | float | 边界缓冲区大小（度） | `max(dx, dy)` |
| `SPLIT_LIM` | float | 分割多边形的尺寸限制（度） | `5*max(dx, dy)` |

#### 其他参数

| 参数 | 类型 | 说明 | 默认值 |
|------|------|------|--------|
| `LAKE_TOL` | float | 湖泊移除容差（-1 表示只保留最大水体） | -1 |
| `IS_GLOBAL` | int | 是否为全球网格 (0/1) | 0 |
| `OBSTR_OFFSET` | int | 障碍物偏移 | 1 |
| `show_plots` | int | 是否显示可视化图表 (0/1) | 1 |

### 经度格式支持

工具支持两种经度格式：

- **-180~180 格式**：标准格式，如 `[-180, 180]` 或 `[110, 130]`
- **0~360 格式**：自动转换为 -180~180 格式，如 `[130, 200]` 会转换为 `[130, -160]`

### 边界级别说明

| 级别 | 分辨率 | 多边形数量（全球） | 适用场景 |
|------|--------|-------------------|----------|
| `coarse` | 最低 | ~1,000 | 快速测试 |
| `low` | 低 | ~10,000 | 大尺度区域 |
| `inter` | 中 | ~50,000 | 中等尺度区域 |
| `high` | 高 | ~150,000 | 精细区域 |
| `full` | 最高 | ~190,000 | 最精细区域（推荐） |

## 输出文件

网格生成完成后，会在输出目录生成以下文件：

### 主要输出文件

1. **`grid.bot`**
   - 格式：ASCII 文本文件
   - 内容：网格水深数据（米）
   - 单位：米（实际值 = 文件值 / 1000）
   - 尺寸：Ny × Nx

2. **`grid.mask`**
   - 格式：ASCII 文本文件
   - 内容：陆海掩膜
   - 值：0 = 陆地，1 = 海洋
   - 尺寸：Ny × Nx

3. **`grid.obst`**
   - 格式：ASCII 文本文件
   - 内容：x 和 y 方向的障碍物值
   - 单位：0-1 之间的比例（实际值 = 文件值 / 100）
   - 尺寸：Ny × Nx（x 方向），Ny × Nx（y 方向）

4. **`grid.meta`**
   - 格式：ASCII 文本文件
   - 内容：网格元数据
   - 包含：网格尺寸、分辨率、范围、投影信息等

### 可视化文件

工具会在输出目录的 `photo` 子目录生成以下可视化图片：

- `grid_bathymetry.png`：水深分布图
- `grid_mask.png`：陆海掩膜图
- `grid_obstruction_x.png`：X 方向障碍物图
- `grid_obstruction_y.png`：Y 方向障碍物图

## 常见问题

### 1. 经度范围错误

**问题**：`ERROR: Longitudes (110,180) beyond range (-179.997,179.997)`

**解决方案**：
- 工具已自动处理边界情况（180 度会自动修正为 179.997）
- 如果仍出现错误，检查输入经度范围是否正确

### 2. 边界数据未找到

**问题**：`Boundary file not found` 或 `coastal_bound_*.mat not found`

**解决方案**：
- 确保已运行 `get_reference_data.sh` 脚本下载参考数据
- 检查 `reference_data` 目录是否包含以下文件：
  - `coastal_bound_full.mat`
  - `coastal_bound_high.mat`
  - `coastal_bound_inter.mat`
  - `coastal_bound_low.mat`
  - `coastal_bound_coarse.mat`
- 如果文件缺失，重新运行 `get_reference_data.sh` 或手动下载并解压 `gridgen_addit.tar.gz`
- 检查 `boundary` 参数是否正确（`full`, `high`, `inter`, `low`, `coarse`）

### 3. 水深数据未找到

**问题**：`Bathymetry file not found` 或 `gebco.nc not found`

**解决方案**：
- 确保已运行 `get_reference_data.sh` 脚本下载参考数据
- 检查 `reference_data` 目录是否包含相应的 `.nc` 文件：
  - `gebco.nc`（GEBCO 2025 数据，推荐）
  - `etopo1.nc`（ETOPO1 数据，可选）
  - `etopo2.nc`（ETOPO2 数据，可选）
- 如果 `gebco.nc` 缺失，重新运行 `get_reference_data.sh` 或手动下载并解压 `gebco_2025_sub_ice_topo.zip`
- 确保解压后的文件名为 `gebco.nc`（可能需要重命名）
- 检查 `ref_grid` 参数是否正确（`gebco`, `etopo1`, `etopo2`）

### 4. 执行缓慢

**问题**：执行很慢，CPU 利用率低

**解决方案**：
- 工具已优化，使用多进程并行处理
- 确保系统有足够的 CPU 核心
- 检查是否有其他进程占用资源

### 5. 小岛屿未显示

**问题**：生成的地图中小岛屿缺失或面积缩小

**解决方案**：
- 使用 `boundary='full'` 获取最高分辨率边界数据
- 检查 `LIM_VAL` 参数，可能需要降低阈值（如 0.3）
- 检查 `OFFSET` 参数，确保边界缓冲区足够

## 性能优化

工具已实现以下优化：

1. **多进程并行处理**：
   - Step 3（生成水深）：向量化操作
   - Step 9（计算障碍物）：多进程并行处理 wet cells

2. **算法优化**：
   - 预计算 cell paths 和边界框
   - 批量处理边界点
   - 减少重复计算

3. **内存优化**：
   - 分批处理大数据集
   - 及时释放不需要的数据

### 性能建议

- **小网格**（< 100×100）：处理速度较快
- **中等网格**（100×100 到 500×500）：多进程优势明显
- **大网格**（> 500×500）：多进程并行显著提升性能

## 工作流程

网格生成包含以下步骤：

1. **Step 1: 定义网格坐标**
   - 根据 `dx`, `dy`, `lon_range`, `lat_range` 生成网格点坐标

2. **Step 2: 读取 GSHHS 边界数据**
   - 加载指定级别的海岸线多边形数据

3. **Step 3: 生成水深数据**
   - 从全球水深数据集插值/平均生成网格水深

4. **Step 4: 计算网格域内的边界**
   - 识别与网格域相交的海岸线多边形

5. **Step 5: 创建初始陆海掩膜**
   - 基于水深数据创建初始掩膜

6. **Step 6: 分割大边界多边形**
   - 将大多边形分割为更小的片段以提高处理效率

7. **Step 7: 使用边界多边形清理掩膜**
   - 使用精确的海岸线数据清理初始掩膜

8. **Step 8: 移除湖泊和小水体**
   - 根据 `LAKE_TOL` 参数移除小水体

9. **Step 9: 创建障碍物网格**
   - 计算 x 和 y 方向的波浪传播障碍物

10. **Step 10: 写入输出文件**
    - 生成 WAVEWATCH III 格式的网格文件

## 示例

### 示例 1：生成中国东海网格

```python
import sys
sys.path.append('/path/to/gridgen')
from python.create_grid import create_grid

create_grid(
    dx=0.05,
    dy=0.05,
    lon_range=[120, 130],
    lat_range=[25, 35],
    ref_grid='gebco',
    boundary='full',
    out_dir='./donghai_grid'
)
```

### 示例 2：生成高分辨率局部网格

```python
import sys
sys.path.append('/path/to/gridgen')
from python.create_grid import create_grid

create_grid(
    dx=0.01,
    dy=0.01,
    lon_range=[121, 122],
    lat_range=[31, 32],
    ref_grid='gebco',
    boundary='full',
    LIM_BATHY=0.3,  # 更严格的湿地阈值
    LIM_VAL=0.3,    # 更严格的掩膜阈值
    out_dir='./highres_grid'
)
```

### 示例 3：使用自定义参考数据路径

```python
import sys
sys.path.append('/path/to/gridgen')
from python.create_grid import create_grid

create_grid(
    dx=0.05,
    dy=0.05,
    lon_range=[110, 130],
    lat_range=[10, 30],
    ref_dir='/custom/path/to/reference_data',  # 自定义参考数据目录
    out_dir='/custom/path/to/output'            # 自定义输出目录
)
```

## 参考数据

### 下载参考数据

使用 `get_reference_data.sh` 脚本可以自动下载所需的参考数据：

```bash
cd gridgen
chmod +x get_reference_data.sh
./get_reference_data.sh
```

该脚本会下载：
1. **GSHHS 海岸线边界数据**（`gridgen_addit.tar.gz`）
   - 来源：NOAA WAVEWATCH III 官方 FTP
   - 包含 5 个分辨率级别的边界数据：coarse, low, inter, high, full
   - 解压后生成 `coastal_bound_*.mat` 文件

2. **GEBCO 2025 水深数据**（`gebco_2025_sub_ice_topo.zip`）
   - 来源：CEDA (Centre for Environmental Data Analysis)
   - 全球高分辨率水深数据
   - 解压后需要确保文件名为 `gebco.nc`

### 水深数据源

- **GEBCO 2025**：General Bathymetric Chart of the Oceans 2025，全球海洋水深数据（推荐）
- **ETOPO1**：1 arc-minute 全球地形数据（需要单独下载）
- **ETOPO2**：2 arc-minute 全球地形数据（需要单独下载）

### 边界数据源

- **GSHHS**：Global Self-consistent Hierarchical High-resolution Shoreline
- 提供 5 个分辨率级别：coarse, low, inter, high, full
- 数据包含在 `gridgen_addit.tar.gz` 中

### 参考数据目录结构

下载完成后，`reference_data` 目录应包含：

```
reference_data/
├── coastal_bound_coarse.mat
├── coastal_bound_full.mat
├── coastal_bound_high.mat
├── coastal_bound_inter.mat
├── coastal_bound_low.mat
├── gebco.nc
├── optional_coastal_polygons.mat
└── user_polygons.flag
```


**注意**：本工具生成的网格文件与 WAVEWATCH III 完全兼容，可以直接用于波浪模拟。

