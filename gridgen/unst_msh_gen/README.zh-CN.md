# WAVEWATCH III 非结构网格生成（JIGSAW）

**语言：** [English](README.md) · [简体中文](README.zh-CN.md)

## 说明

用于生成 WAVEWATCH III 非结构三角网格。流程基于 **JIGSAW**，通过 [jigsaw-python](https://github.com/dengwirda/jigsaw-python) 完成剖分。

主要脚本：

- **`ocn_ww3.py`** — 全球网格（均匀或可变分辨率）。
- **`ocn_ww3_regional.py`** — 区域经纬度范围，立体投影 + DEM 子集驱动间距场。

工具仍在演进中；后续会加强可变分辨率相关流程。

**常用网格参数（配置项、单位、推荐组合）：** 见 [`MESH_PARAMS.md`](MESH_PARAMS.md)。

**JSON 配置：** 仓库提供 [`config.json`](config.json)。使用  
`python3 ocn_ww3.py --config config.json` 或 `python3 ocn_ww3_regional.py --config config.json` 时，  
程序从 JSON 读取间距等参数，并**固定**输出 **`grid.msh`**（JIGSAW）与 **`grid.ww3`**（WW3）。  
**`window_mask.py` 仍使用 `config.ini`。**

---

## 安装

### 1. 安装 jigsaw-python

参见 [jigsaw-python](https://github.com/dengwirda/jigsaw-python)（需 CMake 等编译原生库）。

### 2. Python 依赖

常见依赖（另见 `jigsaw-python/requirements.txt`）：

- numpy  
- scipy  
- packaging  
- netCDF4  
- imageio  
- scikit-image  
- tifffile  
- certifi  
- cftime  
- pillow  
- setuptools  

`window_mask.py` 或区域脚本若用到 GIS，可能还需 **geopandas** 等。

### 3. 获取代码

示例（上游仓库布局）：

```bash
git clone https://github.com/NOAA-EMC/WW3-tools
cd WW3-tools/unst_msh_gen
```

在 **WW3Tool** 工程中，本目录位于 `gridgen/unst_msh_gen/`。

### 4. DEM（水深 NetCDF）

下载与配置中 `dem_file` 一致的 DEM，例如：

```bash
wget https://github.com/dengwirda/dem/releases/download/v0.1.1/RTopo_2_0_4_GEBCO_v2023_60sec_pixel.zip
unzip *.zip
```

---

## 使用

### 全球：`ocn_ww3.py`

编辑 **`config.ini`**（或改用下面的 **`config.json`**）：

- **DataFiles：** 在 `dem_file` 指定 bathymetry NetCDF。  
- **Spacing：** **均匀**分辨率时设 `hmax` = `hmin` = `hshr` = `hfun_hmax`（见 `[MeshSettings]`），且 `nwav` = 0。  
- **CommandLineArg — `black_sea`：**  
  - `3` — 黑海及连通  
  - `2` — 黑海为独立海盆  
  - `1` — 不包含黑海  
- **MeshSetting：** 可选 `mesh_file`（JIGSAW）、`ww3_mesh_file`（WW3/Gmsh 类）文件名。

运行：

```bash
python3 ocn_ww3.py --config config.ini
python3 ocn_ww3.py --config config.json   # 固定输出 grid.msh、grid.ww3
```

### 区域经纬度范围

对**有界**区域（如 110–130°E、10–30°N），可复制并编辑 **`config_regional.ini`**（`[Regional]` + `[Spacing]`），或使用带 **`"regional": { ... }`** 的 **`config.json`**。

```bash
python3 ocn_ww3_regional.py --config config_regional.ini
python3 ocn_ww3_regional.py --config config.json
```

使用立体投影与 DEM **子集** 生成间距场；最终网格上的水深仍通过 **`inject_dem`** 从完整 DEM 映射。

**macOS：** 若 **`marche`** 报 `**input error**`，可尝试 **Debug** 版 JIGSAW（Release 可能启用 `-ffinite-math-only`，与 `infinity()` 检查冲突）。

**输出：** WW3 使用 `ww3_mesh_file` 指定的 Gmsh 兼容网格。

**经度：** 输出为 **−180…180°**。若需 **0…360°**，使用 **`ShiftMesh.py`**：

- `input_file_path` — −180…180° 的网格  
- `output_file_path` — 0…360° 的网格  

---

### 可变分辨率（`window_mask.py` + 掩膜）

编辑 **`config.ini`**：

- 若要在**美国岸线**等处加密，可用 JSON 定义窗口区域，并在 **DataFiles** 中设置 **`window_file`**。  

**注意：** `hshr` 为**岸线**尺度，可以比全局 `hmin` **更细**。

- **`window_mask.py`** 可读取 JSON 形式 shapefile，并为多边形指定 **scale**；在 **DataFiles** 中设置 **`shape_file`**。  
- 可在 QGIS/ArcGIS 中制作多边形，放入 `./Shapefiles`，为每个多边形指定不同分辨率。  
- 亦可按纬度带设置背景分辨率，见 **`window_mask.py`** 与 **`config.ini`** 的 **`ScalingSettings`**：

| 键 | 含义 |
|----|------|
| `upper_bound` | 北纬超过该值进入“北部”带宽 |
| `middle_bound` | 中与南带分界；中带为 `middle_bound` 与 `upper_bound` 之间 |
| `lower_bound` | 南侧边界（多为 −90°）；南带为 `lower_bound` 与 `middle_bound` 之间 |
| `scale_north` | 纬向 > `upper_bound` 时的间距（km） |
| `scale_middle` | `middle_bound` < lat < `upper_bound` 时的间距（km） |
| `scale_south_upper` / `scale_south_lower` | 南带内间距（km）线性过渡 |

运行：

```bash
python3 window_mask.py --config config.ini
```

输出：**`wmask.nc`**（间距场）。

要让 **`ocn_ww3.py`** 使用该间距，在 **`config.ini`** 中设 **`mask_file = wmask.nc`**，再执行：

```bash
python3 ocn_ww3.py --config config.ini
```

---

### 绘图

- **`plot_msh.py`** 读取 Gmsh 风格 **`grid.msh`** / **`grid.ww3`**（默认 `./grid.ww3`）。范围由节点经纬度外包络（加边距）决定，可用 **`--extent`** 覆盖。  
- 示例：  
  `python3 plot_msh.py --descriptor myrun`  
  `python3 plot_msh.py --filename grid.msh --descriptor myrun --margin-deg 0.5`

---

## 贡献

由 Ali Salimi-Tarazouj 持续维护，并得到 JIGSAW 作者 Darren Engwirda 的大力支持。
