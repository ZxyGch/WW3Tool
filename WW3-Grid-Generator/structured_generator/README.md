# WAVEWATCH III Structured Grid Generator

**WAVEWATCH III structured grid generator** — rectangular / curvilinear grids (bathymetry, mask, obstructions) for WW3.

- **Original source code:** [Ifremer gridgen](https://gitlab.ifremer.fr/wave/tools/gridgen) (GNU GPL v3.0 or later).
- **`pygridgen/`:** Python implementation **obtained by AI-assisted conversion** from the original codebase (MATLAB and related sources in **`gridgen/`** remain the reference ports from that project).

Python-based workflow alongside the MATLAB **`gridgen/`** tree; both target WAVEWATCH III–compatible outputs.

**Languages:** [English](README.md) · [简体中文](README.zh-CN.md)

## Contents

- [Overview](#overview)
- [Requirements](#requirements)
- [Installation](#installation)
- [Quick start](#quick-start)
- [Parameters](#parameters)
- [Output files](#output-files)
- [Troubleshooting](#troubleshooting)
- [Performance](#performance)
- [Workflow](#workflow)
- [Examples](#examples)
- [Reference data](#reference-data)

## Overview

This package is a **structured grid generator** for the **WAVEWATCH III (WW3) wave model**: it prepares WW3-ready grid files (bathymetry, masks, obstructions) on regular or curvilinear meshes. Use **`gridgen/`** for the MATLAB workflow and **`pygridgen/`** for Python (see provenance at the top).

It produces:

- **Bathymetry** — from global datasets (GEBCO, ETOPO1, ETOPO2)
- **Land–sea mask** — from GSHHS coastlines
- **Obstruction grids** — coastal blocking of wave propagation (x/y components)

### Features

1. Regular or curvilinear grid coordinates  
2. Bathymetry by interpolation / cell averaging from global DEMs  
3. Boundary handling with GSHHS polygons  
4. Mask cleanup using coastline polygons  
5. Obstruction fields along x and y  

## Requirements

- Python 3.7+ (3.9+ recommended)  
- Packages:

  ```
  numpy >= 1.19.0
  scipy >= 1.5.0
  netCDF4 >= 1.5.0
  matplotlib >= 3.3.0
  ```

## Installation

### 1. Download reference data

Bathymetry and coastline data are required before running.

**Default — GitHub bundle (recommended)**

From the repository root `WW3-Grid-Generator/`, run:

```bash
cd WW3-Grid-Generator
python3 get_reference_data.py
```

This downloads the `data` release split archive from **GitHub** (`part_aa` … `part_ad`), merges it into `reference_data.zip`, and extracts into `reference_data/`.  
For upstream multi-source fetch instead, use: `python3 get_reference_data.py --legacy` (slower; not required for the usual bundle).

**Optional — manual download**

If the GitHub download is slow or blocked, use a full **`reference_data.zip`** (or equivalent) from mirrors, then extract so that `WW3-Grid-Generator/reference_data/` contains the expected files (see [Reference data](#reference-data)):

- **Ydray:** <https://ydray.com/get/t/u17741446196277XguE91036edeefddAV>
- **OneDrive:** <https://tiangongeducn-my.sharepoint.com/:u:/r/personal/1911650207_tiangong_edu_cn/Documents/reference_data.zip?csf=1&web=1&e=SXDbA9>
- **Baidu Netdisk:** <https://pan.baidu.com/s/1SxQEfiaomdi3CXFOXC6DMw?pwd=cb48> (code: `cb48`)

Create the folder if needed: `mkdir -p WW3-Grid-Generator/reference_data`.

### 2. Python dependencies

```bash
pip install numpy scipy netcdf4 matplotlib
```

## Quick start

Call `create_grid` with arguments; no separate config file is required.

```python
import sys
sys.path.append('/path/to/WW3-Grid-Generator/structured_generator/pygridgen')
from python.create_grid import create_grid

create_grid(
    dx=0.05,
    dy=0.05,
    lon_range=[110, 130],
    lat_range=[10, 30],
    out_dir='./output'
)

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

**Notes**

- Add `WW3-Grid-Generator/structured_generator/pygridgen` to `sys.path` (or install as a package)  
- Default reference dir: `WW3-Grid-Generator/reference_data/`; default output: `WW3-Grid-Generator/result/`  
- Override with `ref_dir` and `out_dir`  

## Parameters

### Required

| Parameter | Type | Description | Default |
|-----------|------|-------------|---------|
| `dx` | float | Longitude resolution (deg) | 0.05 |
| `dy` | float | Latitude resolution (deg) | 0.05 |
| `lon_range` | list | [west, east] | [110, 130] |
| `lat_range` | list | [south, north] | [10, 30] |

### Optional — paths

| Parameter | Type | Description | Default |
|-----------|------|-------------|---------|
| `bin_dir` | str | Bin directory | `../bin/` |
| `ref_dir` | str | Reference data directory | `../reference_data/` |
| `out_dir` | str | Output directory | `../result/` |
| `fname` | str | Output name prefix | `grid` |

### Optional — bathymetry

| Parameter | Type | Description | Default |
|-----------|------|-------------|---------|
| `ref_grid` | str | Source: `gebco`, `etopo1`, `etopo2` | `gebco` |
| `LIM_BATHY` | float | Fraction of cell that must be wet | 0.1 |
| `CUT_OFF` | float | Depth threshold wet/dry (m) | 0.1 |
| `DRY_VAL` | float | Depth value on dry cells | 999999 |

### Optional — coastlines

| Parameter | Type | Description | Default |
|-----------|------|-------------|---------|
| `boundary` | str | GSHHS level: `full`, `high`, `inter`, `low`, `coarse` | `full` |
| `read_boundary` | int | Read boundary data (0/1) | 1 |
| `opt_poly` | int | Use optional polygons (0/1) | 0 |
| `fname_poly` | str | Optional polygon flag file | `user_polygons.flag` |
| `LIM_VAL` | float | Polygon mask fraction threshold | 0.5 |
| `OFFSET` | float | Coast buffer (deg) | `max(dx, dy)` |
| `SPLIT_LIM` | float | Max polygon split size (deg) | `5*max(dx, dy)` |

### Optional — other

| Parameter | Type | Description | Default |
|-----------|------|-------------|---------|
| `LAKE_TOL` | float | Lake removal tolerance (−1 = keep largest water only) | -1 |
| `IS_GLOBAL` | int | Global grid (0/1) | 0 |
| `OBSTR_OFFSET` | int | Obstruction offset | 1 |
| `show_plots` | int | Show plots (0/1) | 1 |

### Longitude conventions

- **−180…180** — e.g. `[-180, 180]`, `[110, 130]`  
- **0…360** — converted automatically, e.g. `[130, 200]` → `[130, -160]`  

### GSHHS resolution levels

| Level | Detail | ~Polygons (global) | Use case |
|-------|--------|--------------------|----------|
| `coarse` | Lowest | ~1,000 | Quick tests |
| `low` | Low | ~10,000 | Large domains |
| `inter` | Medium | ~50,000 | Regional |
| `high` | High | ~150,000 | Fine regional |
| `full` | Highest | ~190,000 | Recommended default |

## Output files

### Grids (ASCII)

1. **`grid.bot`** — bathymetry (m); stored value ×1000 = metres; size Ny×Nx  
2. **`grid.mask_nobound`** — sea (1) / land (0); Ny×Nx  
3. **`grid.obst`** — obstructions; fraction 0–1 (file value /100); x and y blocks  
4. **`grid.nml`** — WW3 grid description for `ww3_grid` (written by `write_ww3meta`; same as MATLAB/Python `gridgen`)  

### Figures (`photo/`)

- `grid_bathymetry.png`  
- `grid_mask.png`  
- `grid_obstruction_x.png`  
- `grid_obstruction_y.png`  

## Troubleshooting

### Longitude range error

`ERROR: Longitudes (110,180) beyond range (-179.997,179.997)`

- 180° is adjusted internally; verify your `[west, east]` input  

### Boundary files missing

`Boundary file not found` / `coastal_bound_*.mat not found`

- Run `python3 get_reference_data.py` in `WW3-Grid-Generator/`, or install `reference_data` manually (see [Installation](#installation))  
- Expect `coastal_bound_{full,high,inter,low,coarse}.mat` under `reference_data/`  
- Match `boundary` to an existing `coastal_bound_*.mat`  

### Bathymetry missing

`Bathymetry file not found` / `gebco.nc not found`

- Run `python3 get_reference_data.py` or restore `gebco.nc` (and optional `etopo*.nc`) under `reference_data/`  
- Use `ref_grid` consistent with available files (`gebco`, `etopo1`, `etopo2`)  

### Slow runs

- The code uses multiprocessing where applicable; ensure CPU is available  

### Small islands missing

- Use `boundary='full'`  
- Try lower `LIM_VAL` (e.g. 0.3)  
- Increase `OFFSET` if the coast buffer is too tight  

## Performance

1. **Parallelism** — vectorized bathymetry; multiproc obstruction step for wet cells  
2. **Algorithm** — precomputed paths/bboxes, batched boundary work  
3. **Memory** — chunked processing where needed  

**Rules of thumb**

- Small grids (&lt; 100×100): fast  
- Medium (100–500 per side): multiprocessing helps  
- Large (&gt; 500): parallelism matters most  

## Workflow

1. Define coordinates (`dx`, `dy`, `lon_range`, `lat_range`)  
2. Load GSHHS for the chosen `boundary` level  
3. Build bathymetry from the global DEM  
4. Clip coastlines to the domain  
5. Initial wet/dry mask from depth  
6. Split large polygons for efficiency  
7. Refine mask with coastline polygons  
8. Remove lakes / small water bodies (`LAKE_TOL`)  
9. Compute obstruction grids  
10. Write `grid.bot`, `grid.mask_nobound`, `grid.obst`, `grid.nml`  

## Examples

### East China Sea–style domain

```python
import sys
sys.path.append('/path/to/WW3-Grid-Generator/structured_generator/pygridgen')
from python.create_grid import create_grid

create_grid(
    dx=0.05,
    dy=0.05,
    lon_range=[120, 130],
    lat_range=[25, 35],
    ref_grid='gebco',
    boundary='full',
    out_dir='./east_china_sea_grid'
)
```

### High-resolution local window

```python
import sys
sys.path.append('/path/to/WW3-Grid-Generator/structured_generator/pygridgen')
from python.create_grid import create_grid

create_grid(
    dx=0.01,
    dy=0.01,
    lon_range=[121, 122],
    lat_range=[31, 32],
    ref_grid='gebco',
    boundary='full',
    LIM_BATHY=0.3,
    LIM_VAL=0.3,
    out_dir='./highres_grid'
)
```

### Custom reference and output paths

```python
import sys
sys.path.append('/path/to/WW3-Grid-Generator/structured_generator/pygridgen')
from python.create_grid import create_grid

create_grid(
    dx=0.05,
    dy=0.05,
    lon_range=[110, 130],
    lat_range=[10, 30],
    ref_dir='/custom/path/to/reference_data',
    out_dir='/custom/path/to/output'
)
```

## Reference data

### Download

Default: run `python3 get_reference_data.py` under `WW3-Grid-Generator/` (GitHub `data` release bundle).  
Manual mirrors (full archive): see [Installation → Optional — manual download](#1-download-reference-data).

### Contents (typical)

- Bathymetry: **`gebco.nc`** (primary in the bundle); optional **`etopo1.nc`**, **`etopo2.nc`** if you add them  
- Coastlines / masks: **`coastal_bound_*.mat`**, **`optional_coastal_polygons.mat`**, **`user_polygons.flag`**

### Expected `reference_data/` layout

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

Grids produced here are compatible with WAVEWATCH III for wave modelling.
