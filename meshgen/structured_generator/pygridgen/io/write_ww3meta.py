"""
WW3 grid description file — same content as MATLAB ``gridgen/bin/write_ww3meta.m``.

Writes ``grid.meta`` under the output directory (MATLAB may write ``ww3_grid.nml.<fname>``;
callers that need ``grid.meta`` use this module’s output path).
"""

from __future__ import annotations

import importlib.util
import math
import os
import warnings

import netCDF4
import numpy as np

try:
    from .read_namelist import read_namelist
except ImportError:
    _rn = os.path.join(os.path.dirname(os.path.abspath(__file__)), "read_namelist.py")
    _spec = importlib.util.spec_from_file_location("ww3grid_io_rn", _rn)
    if _spec is None or _spec.loader is None:
        raise ImportError(f"Cannot load read_namelist from {_rn}") from None
    _read_namelist_mod = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_read_namelist_mod)
    read_namelist = _read_namelist_mod.read_namelist


def _timesteps_from_grid(lon: np.ndarray, lat: np.ndarray, fmin: float = 0.0339) -> tuple[float, float, float, float]:
    """Match MATLAB write_ww3meta TIMESTEPS block (Fmin default 0.0339)."""
    lon = np.asarray(lon, dtype=float)
    lat = np.asarray(lat, dtype=float)
    minlon = float(np.min(lon))
    maxlon = float(np.max(lon))
    _ny, nx = lon.shape
    reslon = abs(maxlon - minlon) / nx
    minlat = float(np.min(lat))
    maxlat = float(np.max(lat))
    dx = min(
        reslon * math.cos(math.radians(maxlat)) * 1852 * 60,
        reslon * math.cos(math.radians(minlat)) * 1852 * 60,
    )
    tcfl = dx / (9.81 / (fmin * 4 * math.pi))
    max_tcfl = 0.9 * tcfl
    if max_tcfl > 60:
        max_tcfl = round(max_tcfl / 60) * 60
    else:
        max_tcfl = round(max_tcfl / 6) * 6
    tglob = 3 * max_tcfl
    tref = tglob / 6
    tsrc = 1.0
    return tglob, max_tcfl, tref, tsrc


def write_ww3meta(fname, fname_nml, gtype, lon, lat, *args, is_global_override=None, ref_dir_override=None):
    """
    Write ``grid.meta`` with the same blocks and formatting as MATLAB ``write_ww3meta.m``.

    Parameters
    ----------
    fname : str
        Prefix path ``os.path.join(out_dir, grid_basename)`` (no extension), same as MATLAB’s
        ``output_dir`` + file prefix usage for depth/mask/obst names.
    fname_nml : str | None
        Path to grid namelist (``GRID_INIT``, ``OUTGRID``, ``BATHY_FILE``). If ``None``, defaults
        match un-nested Python callers: ``SPHE`` / closure from ``is_global_override``, ``NAME``
        from basename of ``fname``.
    gtype : str
        ``'RECT'`` or ``'CURV'`` (same as MATLAB).
    lon, lat : ndarray
        Grid coordinates (2-D).
    *args :
        ``N1, N2`` depth and obstruction scale factors; optional ``N3`` for CURV coordinate SF;
        optional ``ext1, ext2, ext3`` for depth/mask/obstruction extensions (default ``.bot``,
        ``.obst``, ``.mask``).
    """
    path_prefix = os.path.normpath(fname)
    out_dir = os.path.dirname(path_prefix)
    if not out_dir:
        out_dir = os.getcwd()
    meta_file = os.path.join(out_dir, "grid.meta")
    file_prefix = os.path.basename(path_prefix)

    gtype = (gtype or "RECT").strip()
    gtype_out = gtype.upper()
    if gtype_out not in ("RECT", "CURV"):
        return f"Unsupported grid type: {gtype}", -1

    lon = np.asarray(lon)
    lat = np.asarray(lat)

    # Defaults match the un-nested Python callers; the namelist (when present and
    # readable) refines them. A stale/unreadable namelist or bathymetry file must
    # NOT abort grid.meta writing — geographic grids default to SPHE.
    grid_name = file_prefix
    coord = "'SPHE'"
    isglobal = int(is_global_override) if is_global_override is not None else 0

    if fname_nml is not None:
        try:
            init_nml = read_namelist(fname_nml, "GRID_INIT")
            outgrid_nml = read_namelist(fname_nml, "OUTGRID")
            bathy_nml = read_namelist(fname_nml, "BATHY_FILE")
            grid_name = str(init_nml.get("fname", file_prefix))
            isglobal = int(outgrid_nml.get("is_global", isglobal))
            # Prefer the runtime ref_dir passed by the caller (dynamically computed,
            # authoritative) over the static REF_DIR in the namelist file.
            ref_dir_raw = ref_dir_override if ref_dir_override else init_nml["ref_dir"]
            ref_dir = os.path.normpath(
                os.path.abspath(os.path.expanduser(str(ref_dir_raw).strip().strip("'\"")))
            )
            ref_grid = str(bathy_nml["ref_grid"])
            xvar = str(bathy_nml["xvar"])
            fname_bathy = os.path.normpath(os.path.join(ref_dir, f"{ref_grid}.nc"))
            try:
                with netCDF4.Dataset(fname_bathy, "r") as f:
                    var_lon = f.variables[xvar]
                    try:
                        lon_units = var_lon.units
                    except AttributeError:
                        warnings.warn(
                            "No units attribute for spatial dimensions. Setting units to degree"
                        )
                        lon_units = "degree"
                coord = "'SPHE'" if "degree" in str(lon_units).lower() else "'CART'"
            except Exception as e:
                print(
                    f"!!WARN!!: Cannot read bathymetry file for COORD detection ({e}); "
                    f"defaulting GRID%COORD to {coord}",
                    flush=True,
                )
        except Exception as e:
            print(
                f"!!WARN!!: Cannot read grid namelist '{fname_nml}' ({e}); "
                "using default grid description parameters",
                flush=True,
            )

    # Closure from is_global (namelist) or override; override always wins.
    if is_global_override is not None:
        isglobal = int(is_global_override)
    if isglobal == 1:
        cstrng = "'SMPL'"
    elif isglobal == 0:
        cstrng = "'NONE'"
    else:
        print("!!ERROR!!: Unrecognized Grid Closure")
        return "Unrecognized Grid Closure", -1

    if len(args) < 2:
        return "Missing required arguments N1, N2", -1
    n1 = float(args[0])
    n2 = float(args[1])

    if len(args) >= 6:
        ext1, ext2, ext3 = str(args[3]), str(args[4]), str(args[5])
    else:
        ext1, ext2, ext3 = ".bot", ".obst", ".mask"

    if gtype_out == "CURV":
        if len(args) < 3:
            return "CURV requires N3 (coordinate scale) as third numeric argument", -1
        n3 = float(args[2])
    else:
        n3 = None

    fmin = 0.0339
    tglob, max_tcfl, tref, tsrc = _timesteps_from_grid(lon, lat, fmin)

    try:
        fid = open(meta_file, "w", encoding="utf-8", newline="\n")
    except OSError as e:
        messg = f"Cannot open file: {meta_file}"
        print(f"!!ERROR!!: {messg} ({e})")
        return messg, -1

    def w(s: str) -> None:
        fid.write(s + "\n")

    # --- Match MATLAB fprintf order and formats ---
    w("&SPECTRUM_NML")
    w(f"  SPECTRUM%XFR         =  {1.1:4.2f}")
    w(f"  SPECTRUM%FREQ1       =  {fmin:6.4f}")
    w("  SPECTRUM%NK          =  36")
    w("  SPECTRUM%NTH         =  24")
    w("/")
    w("")

    w("&RUN_NML")
    w("  RUN%FLCX             = T")
    w("  RUN%FLCY             = T")
    w("  RUN%FLCTH            = T")
    w("  RUN%FLCK             = T")
    w("  RUN%FLSOU            = T")
    w("/")
    w("")

    w("&TIMESTEPS_NML")
    w(f"  TIMESTEPS%DTMAX      =  {tglob:5.2f}")
    w(f"  TIMESTEPS%DTXY       =  {max_tcfl:5.2f}")
    w(f"  TIMESTEPS%DTKTH      =  {tref:5.2f}")
    w(f"  TIMESTEPS%DTMIN      =   {tsrc:5.2f}")
    w("/")
    w("")

    w("&GRID_NML")
    w(f"  GRID%NAME            =  '{grid_name}'")
    w("  GRID%NML             =  'namelists.nml'")
    w(f"  GRID%TYPE            =  '{gtype_out}'")
    w(f"  GRID%COORD           =  {coord}")
    w(f"  GRID%CLOS            =  {cstrng}")
    w(f"  GRID%ZLIM            =  {-0.10:5.2f}")
    w(f"  GRID%DMIN            =  {2.5:5.2f}")
    w("/")
    w("")

    ny, nx = lon.shape

    if gtype_out == "RECT":
        w("&RECT_NML")
        w(f"  RECT%NX              =  {nx}")
        w(f"  RECT%NY              =  {ny}")
        sx = float(lon[0, 1] - lon[0, 0])
        sy = float(lat[1, 0] - lat[0, 0])
        x0 = float(lon[0, 0])
        y0 = float(lat[0, 0])
        w(f"  RECT%SX              =  {sx:15.12f}")
        w(f"  RECT%SY              =  {sy:15.12f}")
        w(f"  RECT%X0              =  {x0:8.4f}")
        w(f"  RECT%Y0              =  {y0:8.4f}")
        w("/")
    else:
        w("&CURV_NML")
        w(f"  CURV%NX               =  {nx}")
        w(f"  CURV%NY               =  {ny}")
        w(f"  CURV%XCOORD%SF        =  {n3:5.2f}")
        w(f"  CURV%XCOORD%FILENAME  =  '{file_prefix}.lon'")
        w(f"  CURV%YCOORD%SF        =  {n3:5.2f}")
        w(f"  CURV%YCOORD%FILENAME  =  '{file_prefix}.lat'")
        w("/")

    w("")
    w("&DEPTH_NML")
    w(f"  DEPTH%SF             = {n1:5.3f}")
    w(f"  DEPTH%FILENAME       = '{file_prefix}{ext1}'")
    w("/")
    w("")

    w("&MASK_NML")
    w(f"  MASK%FILENAME        = '{file_prefix}{ext3}_nobound'")
    w("/")
    w("")

    w("&OBST_NML")
    w(f"  OBST%SF              = {n2:5.3f}")
    w(f"  OBST%FILENAME        = '{file_prefix}{ext2}'")
    w("/")
    w("")

    fid.close()
    return "", 0
