# Unstructured grid generator (`unst_msh_gen`)

**Languages:** English ([this page](#english)) · [简体中文](#简体中文)



## Overview (EN)

This unstructured triangular mesh generator wraps **[NOAA-EMC/WW3-tools — `unst_msh_gen](https://github.com/NOAA-EMC/WW3-tools/tree/develop/unst_msh_gen)`**. Meshes produced can be used directly with WAVEWATCH III.

## Quick start (EN)

Build and install **jigsawpy** from the local `**jigsaw-python`** tree (pulling from GitHub for the build is not recommended; compilation may fail).

Build tools: C++ compiler, CMake.

```sh
python jigsaw-python/build.py
```

After JIGSAW builds successfully, run:

```sh
python create_grid.py
```

`create_grid.py` reads configuration from `grid.json` automatically.

## `grid.json` structure (EN)

**Domain**

If `clip_to_bounds` is **true**, `create_grid.py` first **clips** `DataFiles.dem_file` to the lat–lon box in the mesh workspace (producing `_clipped_dem.nc`), then runs `ocn_ww3.py`. If `**[Regional]`** is configured, this step is skipped (the regional flow controls extent). **dry-run** does not clip the DEM; the resolved INI still references the original `dem_file`.


| Variable         | Description                                                                                                                                       |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| `clip_to_bounds` | If **true**, clip the DEM to the lat–lon box below (requires `south_lat < north_lat`, `west_lon < east_lon`; dateline crossing is not supported). |
| `west_lon`       | Western boundary longitude for clipping.                                                                                                          |
| `east_lon`       | Eastern boundary longitude for clipping.                                                                                                          |
| `south_lat`      | Southern boundary latitude for clipping.                                                                                                          |
| `north_lat`      | Northern boundary latitude for clipping.                                                                                                          |


**Zoom**

Gaussian refinement “zoom” logic for `create_siz` is written to the resolved INI; with `**zoom_auto_center`** **true**, the **DEM lon/lat midpoints** are used; if **false**, `**zoom_lon_deg`** / `**zoom_lat_deg**` are used.


| Variable           | Description                                                                                 |
| ------------------ | ------------------------------------------------------------------------------------------- |
| `zoom_auto_center` | Default **true**: zoom center is taken from DEM lon/lat midpoints.                          |
| `zoom_lon_deg`     | Zoom center longitude (degrees) when `zoom_auto_center` is **false**; default about `30.5`. |
| `zoom_lat_deg`     | Zoom center latitude (degrees) when `zoom_auto_center` is **false**; default about `41.5`.  |


**Workflow**


| Variable               | Description                                                                                           |
| ---------------------- | ----------------------------------------------------------------------------------------------------- |
| `run_window_mask`      | If **true**, run `window_mask.py` before the main mesh step (requires `unst_msh_gen/window_mask.py`). |
| `unst_msh_gen_dir`     | Relative or absolute path to the `**unst_msh_gen`** tool directory (default `unst_msh_gen`).          |
| `resolved_config_name` | Resolved INI filename written by `create_grid.py` for subprocesses (default `.grid_run.ini`).         |
| `jigsaw_python_root`   | Root of `**jigsaw-python**` containing `jigsawpy/`; used for `PYTHONPATH` and optional auto-build.    |


**Output**


| Variable               | Description                                                                                                 |
| ---------------------- | ----------------------------------------------------------------------------------------------------------- |
| `mesh_workspace_dir`   | **cwd** for `window_mask` / `ocn_ww3` (output dir for e.g. `wmask.nc`, JIGSAW `.msh`, intermediate `.ww3`). |
| `ww3_publish_dir`      | If set: after success, copy the WW3 mesh **to** this directory.                                             |
| `ww3_publish_basename` | Filename for publishing (e.g. `grid.ww3`).                                                                  |


**Spacing**

Units / non-dimensional meaning match upstream `ocn_ww3.py` and `spacing`.


| Variable                 | Description                                                                                                                                |
| ------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------ |
| `hmax`                   | Maximum spacing (km).                                                                                                                      |
| `hshr`                   | Target shoreline spacing (km).                                                                                                             |
| `nwav`                   | Resolution parameter tied to shallow-water wavelength heuristic (0 disables that heuristic).                                               |
| `hmin`                   | Minimum spacing (km).                                                                                                                      |
| `dhdx`                   | Allowed bathymetry-related spacing gradient (smaller gives smoother transitions).                                                          |
| `deep_ocean_threshold_m` | Deep-water threshold (m); used for deep-water spacing correction in the **regional** flow (`create_grid.py`), written to the resolved INI. |


**ScalingSettings**

Read only by `**window_mask.py`**, for latitude-band masks / scaling factors.


| Variable            | Description                                                                         |
| ------------------- | ----------------------------------------------------------------------------------- |
| `upper_bound`       | Latitude upper bound (°): north of this uses `scale_north`.                         |
| `middle_bound`      | Latitude divider (°): between `middle_bound` and `upper_bound` uses `scale_middle`. |
| `lower_bound`       | Latitude lower bound (°): lower end of the southern interpolation interval.         |
| `scale_north`       | Scale factor for the northern band.                                                 |
| `scale_middle`      | Scale factor for the middle band.                                                   |
| `scale_south_upper` | Upper scale factor for the southern interpolation band.                             |
| `scale_south_lower` | Lower scale factor for the southern interpolation band.                             |


**MeshSettings**


| Variable        | Description                                                                           |
| --------------- | ------------------------------------------------------------------------------------- |
| `hfun_hmax`     | Global max mesh size passed to JIGSAW (same as `opts.hfun_hmax` / `HFUN_HMAX`).       |
| `mesh_file`     | Path to JIGSAW output `.msh` (resolved relative to `mesh_workspace_dir` if relative). |
| `ww3_mesh_file` | Path to intermediate WW3 triangular mesh (`.ww3`).                                    |


**CommandLineArgs**


| Variable    | Description                                                                                  |
| ----------- | -------------------------------------------------------------------------------------------- |
| `black_sea` | Integer parameter for Black Sea–type connected-domain handling (same as upstream `ocn_ww3`). |
| `mask_file` | Mask/weight NetCDF for variable spacing (e.g. `wmask.nc`); path resolved from workspace.     |


**DataFiles**


| Variable      | Description                                                                                                                                               |
| ------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `dem_file`    | **Required**: bathymetry DEM (NetCDF with `lon`, `lat`, `bed_elevation`, etc.; same as `ocn_ww3`). Relative paths resolve from the `grid.json` directory. |
| `shape_file`  | **Optional**: polygon scaling for `window_mask`; value is JSON string or object array with entries like `{ "path", "scale" }`.                            |
| `window_file` | **Optional**: rectangular-window JSON for `window_mask` (keys include `min_lon`, `max_lon`, `min_lat`, `max_lat`, etc.).                                  |


Keys or sections whose names start with `**_`** are ignored (reserved for metadata).

---

## 简体中文



# 非结构网格生成器

**语言：** [English](#english) · 简体中文（本文）

## 概述

本非结构化三角网格生成器是对 [NOAA-EMC/WW3-tools — `unst_msh_gen](https://github.com/NOAA-EMC/WW3-tools/tree/develop/unst_msh_gen)` 的二次封装，生成的网格文件可直接用于 WAVEWATCH III.

## 快速开始

**jigsawpy** 请从本地 `**jigsaw-python`** 构建安装(不建议拉取 github 的，编译可能失败)

编译工具：C++ 编译器,CMake 

```sh
python jigsaw-python/build.py
```

jigsaw 编译成功后，执行

```sh
python create_grid.py
```

create_grid.py 会自动读取 grid.json 的配置

## grid.json 结构

**Domain**

若 `clip_to_bounds` 为 **true**，`create_grid.py` 会先在网格工作区将 `DataFiles.dem_file` **裁剪**到裁剪框（生成 `_clipped_dem.nc`），再运行 `ocn_ww3.py`。若配置了 `**[Regional]`** 则跳过此处（由区域流程自行控制范围）。**dry-run** 不裁剪 DEM，解析出的 INI 中仍为原始 `dem_file`。


| 变量               | 说明                                                                                      |
| ---------------- | --------------------------------------------------------------------------------------- |
| `clip_to_bounds` | 若为 **true**，按下列经纬度框裁剪 DEM（须满足 `south_lat < north_lat`、`west_lon < east_lon`，且暂不支持跨日界线）。 |
| `west_lon`       | 裁剪西边界经度。                                                                                |
| `east_lon`       | 裁剪东边界经度。                                                                                |
| `south_lat`      | 裁剪南边界纬度。                                                                                |
| `north_lat`      | 裁剪北边界纬度。                                                                                |


**Zoom**

`create_siz` 中的高斯细化「zoom」逻辑写入解析后的 INI；`**zoom_auto_center`** 为 **true** 时使用 **DEM 经纬度中点**，为 **false** 时使用 `**zoom_lon_deg`** / `**zoom_lat_deg**`。


| 变量                 | 说明                                                           |
| ------------------ | ------------------------------------------------------------ |
| `zoom_auto_center` | 默认 **true**：zoom 中心取 DEM 的经纬度中点。                             |
| `zoom_lon_deg`     | `zoom_auto_center` 为 **false** 时使用的 zoom 中心经度（度）；默认约 `30.5`。 |
| `zoom_lat_deg`     | `zoom_auto_center` 为 **false** 时使用的 zoom 中心纬度（度）；默认约 `41.5`。 |


**Workflow**


| 变量                     | 说明                                                                        |
| ---------------------- | ------------------------------------------------------------------------- |
| `run_window_mask`      | 若为 **true**，在生成主网格前先运行 `window_mask.py`（需 `unst_msh_gen/window_mask.py`）。 |
| `unst_msh_gen_dir`     | 指向 `**unst_msh_gen`** 工具目录的相对/绝对路径（默认 `unst_msh_gen`）。                    |
| `resolved_config_name` | `create_grid.py` 写出、供子进程读取的解析后 INI 文件名（默认 `.grid_run.ini`）。               |
| `jigsaw_python_root`   | 含 `jigsawpy/` 的 `**jigsaw-python**` 根目录；用于 `PYTHONPATH` 与可选自动编译。          |


**Output**


| 变量                     | 说明                                                                                   |
| ---------------------- | ------------------------------------------------------------------------------------ |
| `mesh_workspace_dir`   | `window_mask` / `ocn_ww3` 等工作时的 **cwd**（如 `wmask.nc`、JIGSAW `.msh`、中间 `.ww3` 等输出目录）。 |
| `ww3_publish_dir`      | 若配置：流程成功后将 WW3 网格 **复制**到该目录。                                                        |
| `ww3_publish_basename` | 发布时的文件名（如 `grid.ww3`）。                                                               |


**Spacing**

单位 / 无量纲含义与上游 `ocn_ww3.py`、`spacing` 一致。


| 变量                       | 说明                                                           |
| ------------------------ | ------------------------------------------------------------ |
| `hmax`                   | 最大间距（km）。                                                    |
| `hshr`                   | 岸界附近目标间距（km）。                                                |
| `nwav`                   | 与浅水波长启发式相关的分辨率参数（0 可关闭该启发式）。                                 |
| `hmin`                   | 最小间距（km）。                                                    |
| `dhdx`                   | 允许的海拔相关间距梯度（较小则更平缓）。                                         |
| `deep_ocean_threshold_m` | 深水阈值（m）；**区域**网格流程中用于深水区间距修正（见 `create_grid.py`），并写入解析后 INI。 |


**ScalingSettings**

仅由 `**window_mask.py`** 读取，用于按纬度带对掩膜/缩放因子分区。


| 变量                  | 说明                                                            |
| ------------------- | ------------------------------------------------------------- |
| `upper_bound`       | 纬度上界（°）：高于此纬度用 `scale_north`。                                 |
| `middle_bound`      | 纬度分界（°）：介于 `middle_bound` 与 `upper_bound` 之间用 `scale_middle`。 |
| `lower_bound`       | 纬度下界（°）：用于南侧插值区间的下端。                                          |
| `scale_north`       | 最北纬带的缩放因子。                                                    |
| `scale_middle`      | 中间纬带的缩放因子。                                                    |
| `scale_south_upper` | 南侧插值带的上端缩放因子。                                                 |
| `scale_south_lower` | 南侧插值带的下端缩放因子。                                                 |


**MeshSettings**


| 变量              | 说明                                                        |
| --------------- | --------------------------------------------------------- |
| `hfun_hmax`     | 传给 JIGSAW 的全局最大网格尺度（与 `opts.hfun_hmax` / `HFUN_HMAX` 一致）。 |
| `mesh_file`     | JIGSAW 输出的 `.msh` 路径（可相对 `mesh_workspace_dir` 解析）。        |
| `ww3_mesh_file` | 中间 WW3 三角网文件路径（`.ww3`）。                                   |


**CommandLineArgs**


| 变量          | 说明                                            |
| ----------- | --------------------------------------------- |
| `black_sea` | 黑海等连通域处理相关整数参数（与上游 `ocn_ww3` 一致）。             |
| `mask_file` | 可变间距时输出的掩膜/权重 NetCDF（如 `wmask.nc`）；路径相对工作区解析。 |


**DataFiles**


| 变量            | 说明                                                                                               |
| ------------- | ------------------------------------------------------------------------------------------------ |
| `dem_file`    | **必选**：水深 DEM（NetCDF，须含 `lon`、`lat`、`bed_elevation` 等；与 `ocn_ww3` 一致）。相对路径相对 `grid.json` 所在目录解析。 |
| `shape_file`  | **可选**：`window_mask` 用多边形缩放；值为 JSON 字符串或对象数组，元素可为 `{ "path", "scale" }`。                         |
| `window_file` | **可选**：`window_mask` 用矩形窗 JSON（键含 `min_lon`、`max_lon`、`min_lat`、`max_lat` 等）。                    |


名称以 `**_`** 开头的键或小节会被忽略（预留给元数据）。