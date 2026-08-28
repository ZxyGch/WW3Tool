# WAVEWATCH III Structured Grid Generator

**Languages:** [English](#english) · [简体中文](README.zh-CN.md)


## English

### Overview

This tool is a **structured grid generator** for the **WAVEWATCH III (WW3) wave model**: it prepares model-ready grid files (bathymetry, mask, obstructions, etc.) on rectilinear or curvilinear meshes for WW3 pre-processing and runs.

### Output files

- **grid.bot (bathymetry)**: from high-resolution global bathymetry datasets (GEBCO, ETOPO1, ETOPO2)
- **grid.mask_nobound (land–sea mask)**: from GSHHS coastline data
- **grid.obst (obstruction grid)**: coastal blocking of wave propagation
- **grid.meta (grid configuration)**: `ww3_grid.nml` configuration

There are two code stacks: **gridgen** is the original [Ifremer code (MATLAB)](https://gitlab.ifremer.fr/wave/tools/gridgen); **pygridgen** is Python code produced with AI-assisted conversion from that baseline. The final grids differ slightly between the two.

### Main features

1. **Grid coordinates**: regular or curvilinear mesh coordinates
2. **Bathymetry**: interpolate / cell-average from global bathymetry datasets
3. **Boundaries**: use GSHHS coastlines to identify and treat land boundaries
4. **Mask cleanup**: use boundary polygons to clean the initial land–sea mask
5. **Obstructions**: compute x- and y-direction wave-propagation obstructions



### Download reference data

You need `reference_data` ready first (bathymetry, coastline-related `.mat` / `.nc`, etc.).

Run:

```bash
cd meshgen
python3 get_reference_data.py
```


### Quick start

For **gridgen**, open MATLAB and run `create_grid.m` directly.

For **pygridgen**:

```bash
cd structured_generator/pygridgen
python create_grid.py
```

### Parameters

Edit `gridgen/grid.nml` and `pygridgen/grid.nml`.

`create_grid` reads `grid.nml` by default.

### Longitude conventions and the seam (pygridgen)

The target grid may be written either 0..360 or -180..180 regardless of which
convention the bathymetry file uses: `create_grid` reads the convention from
the file and shifts `LON_WEST` / `LON_EAST` to match. (The `LONFROM` namelist
entry is not consulted.) GEBCO ships -180..180, ETOPO1 ships 0..360, ETOPO2
ships -180..180.

For a global bathymetry file the cell sitting on the seam (180 for a
-180..180 base, 0/360 for a 0..360 base) is averaged and interpolated across
the wrap, so it uses the full cell rather than the half that happens to fall
inside the array. Grids that cross that seam therefore differ from output
produced before this was fixed — in exactly one column, by up to a few hundred
metres of depth. Regional grids that do not reach the seam are unaffected.

### Parallelism (pygridgen)

Boundary splitting, mask cleanup, bathymetry averaging and obstruction generation
run across worker processes. The worker count is resolved in this order:

1. `WW3TOOL_MESHGEN_WORKERS` — explicit override
2. `SLURM_CPUS_PER_TASK` / `SLURM_CPUS_ON_NODE` — the CPUs the job was allocated
3. the scheduler affinity mask (`sched_getaffinity`, i.e. cgroup / cpuset limits)
4. `os.cpu_count()`

Under Slurm, request the cores you want with `--cpus-per-task`; the generator picks
them up on its own. `os.cpu_count()` is only the last resort because it reports every
core of the node rather than the cores the job owns.

```bash
srun --cpus-per-task=32 --mem=64G python create_grid.py
# or pin it explicitly
WW3TOOL_MESHGEN_WORKERS=16 python create_grid.py
```

Small grids stay single-process on purpose: each stage only spreads out once there is
enough work to pay back starting the pool. Setting `WW3TOOL_MESHGEN_WORKERS=1` forces
fully serial execution, which is the easiest way to compare against older output.



### Output files (detail)

After generation, the output directory contains:

1. **`grid.bot`**
   - Format: ASCII text
   - Content: grid bathymetry
   - Units: metres (actual value = file value / 1000)
   - Size: Ny × Nx

2. **`grid.mask_nobound`**
   - Format: ASCII text
   - Content: land–sea mask
   - Values: 0 = land, 1 = sea
   - Size: Ny × Nx

3. **`grid.obst`**
   - Format: ASCII text
   - Content: obstruction values in x and y
   - Units: fraction 0–1 (actual value = file value / 100)
   - Size: Ny × Nx (x block), Ny × Nx (y block)

4. **`grid.meta`** (Actually, its format is NML, which will be synced to ww3_grid.nml.)
   - Format: ASCII text
   - Content: grid description for WAVEWATCH III `ww3_grid`
   - Includes: grid size, resolution, extent, etc.

---

# WAVEWATCH III 结构化网格生成器

**语言：** [English](README.md) · [简体中文](README.zh-CN.md)


## 概述

本工具是面向 **WAVEWATCH III(WW3)波浪模式** 的 **结构化网格生成器**：在矩形或曲线网格上准备模式所需的网格文件(水深、掩膜、障碍物等)，供 WW3 预处理与运行使用。

### 输出文件：

- **grid.bot(水深文件)**：从高分辨率全球水深数据集(GEBCO、ETOPO1、ETOPO2)生成
- **grid.mask_nobound(陆海掩膜文件)**：基于 GSHHS 海岸线数据生成
- **grid.obst(障碍物网格文件)**：计算海岸线对波浪传播的阻碍效应
- **grid.meta(网格配置信息)**： ww3_grid.nml 配置

有两个版本的代码，gridgen 是原版的 [ifremer 代码(Matlab)](https://gitlab.ifremer.fr/wave/tools/gridgen)，pygridgen 是我用 AI 转换的 Python 代码，最终生成的网格存在一点区别。


### 主要功能

1. **网格坐标定义**：生成规则或曲线网格坐标
2. **水深数据生成**：从全球水深数据集插值/平均生成网格水深
3. **边界处理**：使用 GSHHS 海岸线数据识别和处理陆地边界
4. **掩膜清理**：使用边界多边形清理初始陆海掩膜
5. **障碍物计算**：计算 x 和 y 方向的波浪传播障碍物



## 下载参考数据

开始前需要准备好 `reference_data`(水深、岸线相关 `.mat` / `.nc` 等)。


```bash
cd meshgen
python get_reference_data.py
```




## 快速开始

对于 gridgen，打开 Matlab 直接执行 create_grid.m 即可

对于 pygridgen

```bash
cd structured_generator/pygridgen
python create_grid.py
```

## 参数配置

修改 gridgen/grid.nml 和 pygridgen/grid.nml 即可

create_grid 会默认自动读取 grid.nml

## 经度约定与接缝（pygridgen）

目标网格用 0~360 还是 −180~180 书写都可以，与底图用哪套约定无关：`create_grid` 会从底图文件本身读出约定，并把 `LON_WEST` / `LON_EAST` 平移到一致（命名列表里的 `LONFROM` 不再参与判断）。GEBCO 是 −180~180，ETOPO1 是 0~360，ETOPO2 是 −180~180。

对于全球底图，骑在接缝上的那一列格子（−180~180 底图的 180°、0~360 底图的 0°/360°）现在会跨接缝绕回取平均和插值，用的是整个格子而不是恰好落在数组内的那一半。因此跨接缝的网格与修复前的结果会有差异——差异只出现在这一列，水深最多相差几百米。不触及接缝的区域网格不受影响。

## 并行计算（pygridgen）

边界切分、掩膜清理、水深平均和障碍物生成都会分发到多个工作进程。进程数按以下顺序确定：

1. `WW3TOOL_MESHGEN_WORKERS`：显式指定
2. `SLURM_CPUS_PER_TASK` / `SLURM_CPUS_ON_NODE`：作业实际分配到的核数
3. 调度器亲和性掩码（`sched_getaffinity`，即 cgroup / cpuset 限制）
4. `os.cpu_count()`

在 Slurm 上只需用 `--cpus-per-task` 申请核数，生成器会自动识别。`os.cpu_count()` 放在最后是因为它报告的是整台节点的核数，而不是作业真正拥有的核数，据此开进程会造成超订。

```bash
srun --cpus-per-task=32 --mem=64G python create_grid.py
# 或显式指定
WW3TOOL_MESHGEN_WORKERS=16 python create_grid.py
```

小网格会有意保持单进程：只有当计算量足够抵消进程池启动开销时，各阶段才会真正并行。设置 `WW3TOOL_MESHGEN_WORKERS=1` 可强制完全串行，便于与旧版结果对比。



## 输出文件

网格生成完成后，会在输出目录生成以下文件：

1. **`grid.bot`**
   - 格式：ASCII 文本文件
   - 内容：网格水深数据(来)
   - 单位：来(实际值 = 文件值 / 1000)
   - 尺寸：Ny × Nx

2. **`grid.mask_nobound`**
   - 格式：ASCII 文本文件
   - 内容：陆海掩膜
   - 值：0 = 陆地，1 = 海洋
   - 尺寸：Ny × Nx

3. **`grid.obst`**
   - 格式：ASCII 文本文件
   - 内容：x 和 y 方向的障碍物值
   - 单位：0-1 之间的比例(实际值 = 文件值 / 100)
   - 尺寸：Ny × Nx(x 方向)，Ny × Nx(y 方向)

4. **`grid.meta`**(实际上是 ww3_grid.nml，用于同步一些配置)
   - 格式：ASCII 文本文件
   - 内容：供 WAVEWATCH III `ww3_grid` 使用的网格描述
   - 包含：网格尺寸、分辨率、范围等信息

