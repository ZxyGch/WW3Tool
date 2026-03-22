# Unstructured mesh generation for WAVEWATCH III (JIGSAW)

**Languages:** [English](README.md) · [简体中文](README.zh-CN.md)

## Description

Mesh generation for unstructured WW3 grids. The workflow uses **JIGSAW** via [jigsaw-python](https://github.com/dengwirda/jigsaw-python) for triangulation.

Main capabilities:

- **`ocn_ww3.py`** — global mesh (uniform or variable resolution).
- **`ocn_ww3_regional.py`** — regional lat–lon box with stereographic projection and DEM subset for spacing.

The tool is under active development; future work includes richer variable-resolution workflows.

**Spacing parameters (options, units, suggested combinations):** see [`MESH_PARAMS.md`](MESH_PARAMS.md).

**JSON config:** the repo provides [`config.json`](config.json). With  
`python3 ocn_ww3.py --config config.json` or `python3 ocn_ww3_regional.py --config config.json`,  
spacing and related fields are read from JSON and outputs are **fixed** to **`grid.msh`** (JIGSAW) and **`grid.ww3`** (WW3).  
`window_mask.py` still uses **`config.ini`**.

---

## Installation

### 1. Install jigsaw-python

Follow [jigsaw-python](https://github.com/dengwirda/jigsaw-python) (build the native library with CMake where required).

### 2. Python packages

Typical installs (see also `jigsaw-python/requirements.txt`):

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

`window_mask.py` / regional extras may need **geopandas** and other GIS stack packages.

### 3. Clone / layout

Example (upstream layout):

```bash
git clone https://github.com/NOAA-EMC/WW3-tools
cd WW3-tools/unst_msh_gen
```

In **WW3Tool**, this folder lives under `gridgen/unst_msh_gen/`.

### 4. DEM (bathymetry NetCDF)

Download a compatible DEM (e.g. RTopo/GEBCO blend) and place it where `dem_file` in config points to. Example:

```bash
wget https://github.com/dengwirda/dem/releases/download/v0.1.1/RTopo_2_0_4_GEBCO_v2023_60sec_pixel.zip
unzip *.zip
```

---

## Usage

### Global: `ocn_ww3.py`

Edit **`config.ini`** (or use **`config.json`** as below):

- **DataFiles:** set `dem_file` to your bathymetry NetCDF.  
- **Spacing:** for **uniform** resolution set `hmax` = `hmin` = `hshr` = `hfun_hmax` (see `[MeshSettings]`) and `nwav` = 0.  
- **CommandLineArg — `black_sea`:**  
  - `3` — Black Sea included with connections  
  - `2` — Black Sea as a separate basin  
  - `1` — Black Sea excluded  
- **MeshSetting:** optional `mesh_file` (JIGSAW) and `ww3_mesh_file` (WW3/Gmsh-style) names.

Run:

```bash
python3 ocn_ww3.py --config config.ini
python3 ocn_ww3.py --config config.json   # outputs: grid.msh, grid.ww3
```

### Regional lat–lon box

For a **bounded** domain (e.g. 110–130°E, 10–30°N), copy and edit **`config_regional.ini`** (`[Regional]` + `[Spacing]`), or use **`config.json`** with a `"regional": { ... }` block.

```bash
python3 ocn_ww3_regional.py --config config_regional.ini
python3 ocn_ww3_regional.py --config config.json
```

Stereographic projection and a DEM **subset** drive spacing; bathymetry on the final mesh still uses the full DEM via **`inject_dem`**.

**macOS:** if **`marche`** fails with `**input error**`, try a **Debug** build of JIGSAW (Release may use `-ffinite-math-only`, which conflicts with `infinity()` checks).

**Output:** WW3 uses the mesh specified by `ww3_mesh_file` (Gmsh-compatible format).

**Longitude:** output uses **−180…180°**. To convert to **0…360°**, use **`ShiftMesh.py`**:

- `input_file_path` — mesh with −180…180° longitude  
- `output_file_path` — mesh with 0…360° longitude  

---

### Variable resolution (`window_mask.py` + mask)

Edit **`config.ini`**:

- For **finer mesh near US coasts** (or other regions), define windows in JSON and set **`window_file`** under **DataFiles**.  

**Note:** `hshr` is **shoreline** spacing and may be **smaller** than global `hmin`.

- **`window_mask.py`** can read shapefiles (as JSON) and assign a **scale** per polygon; set **`shape_file`** in **DataFiles**.  
- You can build polygons in QGIS/ArcGIS, place them under `./Shapefiles`, and assign different resolutions per polygon.  
- Background resolution by latitude bands can be set in **`window_mask.py`** via **`config.ini`**, section **`ScalingSettings`**:

| Key | Meaning |
|-----|--------|
| `upper_bound` | Latitude (°N) above which the “north” band applies |
| `middle_bound` | Boundary between middle and south bands; middle = between `middle_bound` and `upper_bound` |
| `lower_bound` | South edge of domain (often −90°); south band = between `lower_bound` and `middle_bound` |
| `scale_north` | Spacing (km) for lat > `upper_bound` |
| `scale_middle` | Spacing (km) for `middle_bound` < lat < `upper_bound` |
| `scale_south_upper` / `scale_south_lower` | South-band spacing (km) varies linearly between these |

Run:

```bash
python3 window_mask.py --config config.ini
```

Output: **`wmask.nc`** (mesh spacing field).

To drive **`ocn_ww3.py`** from that spacing, set **`mask_file = wmask.nc`** in **`config.ini`**, then:

```bash
python3 ocn_ww3.py --config config.ini
```

---

### Plotting

- **`plot_msh.py`** reads Gmsh-style **`grid.msh`** / **`grid.ww3`** (default `./grid.ww3`). Extent follows the node bounding box (with margin); override with **`--extent`**.  
- Examples:  
  `python3 plot_msh.py --descriptor myrun`  
  `python3 plot_msh.py --filename grid.msh --descriptor myrun --margin-deg 0.5`

---

## Contributing

Ongoing work by Ali Salimi-Tarazouj with major support from Darren Engwirda (JIGSAW).
