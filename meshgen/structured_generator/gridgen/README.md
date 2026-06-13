# Gridgen

**Source:** [IFREMER `wave/tools/gridgen`](https://gitlab.ifremer.fr/wave/tools/gridgen) on GitLab.

## Modifications relative to IFREMER gridgen

### NetCDF bathymetry (GEBCO and similar)

Some elevation NetCDF files **do not define** the optional variable attribute `actual_range` on `lon` / `lat`. In that case MATLAB’s `netcdf.getAtt(..., 'actual_range')` fails with **“Attribute not found (NC_ENOTATT)”**.

This tree aligns **`bin/create_grid.m`** and **`bin/generate_grid.m`** with upstream `gridgen`: longitude and latitude **extents are taken from the coordinate variables** via `netcdf.getVar`, then `min` / `max`, instead of reading `actual_range`. That matches common GEBCO releases and avoids the error above.


## Launcher and local namelist

This tree adds two files next to this README (not present in upstream IFREMER gridgen):

- **`create_grid.m`** — launcher that `cd`s into **`bin/`** and calls **`bin/create_grid.m`** with the namelist path below.  
- **`grid.nml`** — working copy of the grid namelist; edit it for your domain and paths, then run **`create_grid`** from this folder in MATLAB.

## License

This software is published under the [GPLv3 license](https://www.gnu.org/licenses/gpl-3.0.en.html)
