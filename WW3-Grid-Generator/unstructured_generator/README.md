# Unstructured grid generator (`unst_msh_gen`)

## Overview

This folder wraps **NOAA EMC `unst_msh_gen`** (JIGSAW / `ocn_ww3.py`) for WW3-style unstructured meshes. The bundled Python tools under **`unst_msh_gen/`** track the upstream tree:

**Source:** [NOAA-EMC/WW3-tools — `unst_msh_gen` (develop branch)](https://github.com/NOAA-EMC/WW3-tools/tree/develop/unst_msh_gen)

Configuration is read from **`grid.json`** (default), optionally **`grid.yaml`** / **`.ini`**, then written as a resolved INI (e.g. next to the grid file) for `ocn_ww3.py`. Regional lat–lon boxes are handled by the sibling module **`regional_mesh.py`** (not part of that upstream snapshot).

## Quick start

1. **Python** (use one interpreter for everything; avoid mixing Homebrew vs python.org):

   ```bash
   cd WW3-Grid-Generator/unstructured_generator
   python3 -m venv .venv
   source .venv/bin/activate   # Windows: .venv\Scripts\activate
   python3 -m pip install -r requirements.txt
   ```

   Install **jigsawpy** from your local **`jigsaw-python`** build or via `pip install jigsawpy` if you use upstream wheels.

2. **DEM** — RTopo-style NetCDF with variables `lon`, `lat`, `bed_elevation`, `ice_thickness`. Set `DataFiles.dem_file` in `grid.json`. Paths are resolved from the **directory that contains your grid config file** (e.g. default `grid.json` lives in `unstructured_generator/`, so use `../reference_data/...` for `WW3-Grid-Generator/reference_data/`, **not** `../../`, which points at the repo root above `WW3-Grid-Generator/`).

3. **Run**

   ```bash
   python3 create_grid.py
   ```

   Dry-run (write `.grid_run.ini` only):

   ```bash
   python3 create_grid.py --dry-run
   ```

   Custom config path:

   ```bash
   python3 create_grid.py --grid /path/to/grid.json
   ```

## `grid.json` layout

Top-level keys are **INI-style sections**. Standard JSON only (no comments in the file). Field meanings:

| Section | Role |
|--------|------|
| **Domain** | If `clip_to_bounds` is **true**, `create_grid.py` **subsets** `DataFiles.dem_file` to `[west_lon,east_lon]×[south_lat,north_lat]` into the mesh workspace (`_clipped_dem.nc`) before running `ocn_ww3.py`. Skipped when **`[Regional]`** is set (regional solver handles extent). Dry-run does **not** subset; it writes the resolved INI with the original `dem_file`. |
| **Zoom** | Gaussian high-res “zoom” in `create_siz`: **`zoom_auto_center`** (default **true**) uses the **DEM lon/lat midpoints**; if **false**, uses **`zoom_lon_deg`** / **`zoom_lat_deg`** (defaults 30.5 / 41.5). Passed via resolved INI to `ocn_ww3.py`. |
| **Workflow** | `run_window_mask`, `unst_msh_gen_dir`, `resolved_config_name`, `jigsaw_python_root`. |
| **Output** | `mesh_workspace_dir` (cwd for mesh tools), `ww3_publish_dir`, `ww3_publish_basename` (e.g. `grid.ww3`). |
| **Spacing** | `hmax`, `hshr`, `nwav`, `hmin`, `dhdx` (km / non-dim as in upstream). |
| **ScalingSettings** | Latitude-band scales for `window_mask.py` only. |
| **MeshSettings** | `hfun_hmax`, `mesh_file` (`.msh`), `ww3_mesh_file` (intermediate `.ww3`). |
| **CommandLineArgs** | `black_sea`, `mask_file` (`wmask.nc` if variable spacing). |
| **DataFiles** | `dem_file`, optional `shape_file` as JSON string or array of `{ "path", "scale" }`. |

Paths:

- **`dem_file`**, **`Output.*`** (when relative): resolved from the **directory containing `grid.json`**.
- **`mesh_file`**, **`ww3_mesh_file`**, **`mask_file`** (when relative): resolved from **`mesh_workspace_dir`** if set, otherwise from **`unst_msh_gen/`**.

Optional **`shape_file`** in JSON may be a **string** (JSON array text) or a **list** of objects `{"path": "...", "scale": 5}`.

Keys or sections whose names start with **`_`** are ignored (for future metadata).

## Outputs

- With **`Output.mesh_workspace_dir`**: `window_mask` / `ocn_ww3` run with that folder as **cwd** (e.g. `wmask.nc`, JIGSAW `.msh`, intermediate `.ww3`, `geom.msh`, `spac.msh`, `spac.nc`, `test.vtk`).
- With **`Output.ww3_publish_dir`**: after success, the intermediate WW3 mesh is **copied** to `ww3_publish_dir / ww3_publish_basename` (default `grid.ww3`).

## References

- **Upstream repository (canonical `unst_msh_gen` sources):** [github.com/NOAA-EMC/WW3-tools — `unst_msh_gen` @ develop](https://github.com/NOAA-EMC/WW3-tools/tree/develop/unst_msh_gen)
- Local copy notes: `unst_msh_gen/README.md`
- Dependencies: `requirements.txt`
