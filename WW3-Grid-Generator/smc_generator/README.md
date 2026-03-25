# SMC grid generator (`SMCGTools` wrapper)

## Overview

This folder drives **Spherical Multi-Cell (SMC)** grid generation for WW3 using Python routines from **`SMCGTools/PySMCs`** (`smcellgen`, `smcellbdy`). The bundled tree under **`SMCGTools/`** follows the upstream **SMCGTools** project:

**Source:** [ww3-opentools/SMCGTools](https://github.com/ww3-opentools/SMCGTools)

Configuration is read from **`grid.json`** in this directory (or via `-c` / `--config` / `--grid`). Relative paths in JSON are resolved from the **directory that contains `grid.json`**.

The wrapper script is **`create_grid.py`** (not shipped in SMCGTools; it wires bathymetry NetCDF → `smcellgen` / `smcellbdy` and renames outputs).

## Quick start

1. **Python** — install at least **`netCDF4`** and **`pandas`** (same interpreter you use to run the script):

   ```bash
   python3 -m pip install netCDF4 pandas
   ```

2. **Bathymetry** — NetCDF with **1D** `lon` and **1D** `lat`, and a **2D** bathymetry field after squeeze. The grid must be on a **regular** lon/lat spacing (constant `Δlon`, `Δlat`). Set `input.bathymetry_file` in `grid.json`. Example (from `smc_generator/`): `../reference_data/etopo2.nc` → `WW3-Grid-Generator/reference_data/`.

3. **Run**

   ```bash
   cd WW3-Grid-Generator/smc_generator
   python3 create_grid.py
   ```

   Custom config path:

   ```bash
   python3 create_grid.py --grid /path/to/grid.json
   ```

## `grid.json` layout

Top-level keys are fixed sections. Use standard JSON (no comments). Summary:

| Section | Keys | Role |
|--------|------|------|
| **input** | | Bathymetry file and axis handling |
| | `bathymetry_file` | Path to NetCDF (relative to `grid.json`’s directory if not absolute). |
| | `lon_var`, `lat_var`, `bathy_var` | NetCDF variable names; **`null`** lets `create_grid.py` auto-detect from common names (`lon`/`longitude`/…, `lat`/…, `elevation`/`depth`/…). |
| | `bathy_convention` | `"elevation"` (positive up) or `"depth"` / `"depth_positive_down"` / `"positive_down"` (positive down → converted to elevation internally). |
| | `auto_flip_lat`, `auto_flip_lon` | If **true**, flip axis and bathy so lon/lat are increasing (default **true**). |
| | `coord_spacing_rtol`, `coord_spacing_atol` | Tolerance for checking **uniform** `Δlon` / `Δlat` (see `create_grid.py`). |
| | `nan_fill_value` | Replacement for NaNs in bathymetry before calling SMC routines. |
| **grid** | | SMC grid geometry |
| | `name` | Logical grid name (stored in `grid_run_info.json`). |
| | `n_levels` | SMC refinement level count (`mlvlxy0` first entry). |
| | `global` | **true** = global SMC; **false** = regional (requires `regional_bounds`). |
| | `arctic` | **true** = generate Arctic extension (`*BArc.dat` → `grid_arctic_cells.dat`) when global. |
| | `glb_arc_lat` | Arctic latitude parameter (`GlbArcLat`, default like `84.4`). |
| | `origin` | `lon0` / `lat0` (aliases `x0lon` / `y0lat`): SMC origin on the sphere. |
| | `regional_bounds` | Required if `global` is **false**: `west_lon`, `south_lat`, `east_lon`, `north_lat` (aliases `xstart`/`ystart`/… supported in code). |
| **physics** | | Passed into `smcellgen` / `smcellbdy` |
| | `wlevel` | Water level. |
| | `depmin` | Minimum depth / masking threshold context (see SMCGTools docs). |
| | `dshalw` | Shallow-water parameter (`dshalw` in wrapper call). |
| **boundary** | | Regional open boundary |
| | `generate_boundary_cells` | If **true** and **regional** (`global` false), run `smcellbdy` and write `grid_boundary.dat`. |
| | `msea` | Boundary / sea mask parameter for `smcellbdy`. |
| **output** | | |
| | `output_dir` | Directory for final `.dat` / `grid_run_info.json` (relative to `grid.json` parent if not absolute). |
| | `file_prefix` | Present in the sample file for future use; **not** read by `create_grid.py` today. |

## Outputs

Written under **`output.output_dir`** (default `./output` relative to `grid.json`):

| File | Description |
|------|-------------|
| `grid_cell.dat` | SMC inner cells (from temporary `*Cels.dat`). |
| `grid_boundary.dat` | Open-boundary strip only if **`grid.global`** is **false** and **`boundary.generate_boundary_cells`** is **true**. |
| `grid_arctic_cells.dat` | Arctic cells only if **`grid.global`** is **true** and **`grid.arctic`** is **true**. |
| `grid_run_info.json` | Metadata: paths, resolution, variable names, output paths. |

Temporary files use the stem `_smc_generate_tmp*` during the run and are renamed on success.

## References

- **Upstream SMCGTools (canonical sources for `SMCGTools/`):** [github.com/ww3-opentools/SMCGTools](https://github.com/ww3-opentools/SMCGTools)
- Local guides / PDFs: `SMCGTools/SMCGTools_Guide.pdf`, `SMCGTools/SMC_Grids_Guide.pdf`, `SMCGTools/README.md`
