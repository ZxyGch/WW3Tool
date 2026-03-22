
""" Mesh spacing utilities, for barotropic flows
"""

# Authors: Darren Engwirda, Ali Salimi-Tarazouj

# routines to compute mesh spacing functions that scale
# with shallow-water wave lengths, elev. gradients, etc 

import numpy as np
import jigsawpy
import netCDF4 as nc

from skimage.filters import gaussian
from skimage.measure import label, regionprops_table


def align_field_to_shape(arr: np.ndarray, shape: tuple, *, order: int = 1) -> np.ndarray:
    """
    Resize a 2D field to (nrows, ncols). Used when spacing moves from cell-centres
    to corner nodes (+1 in each dimension) so deep-ocean repair can compare like shapes.
    """
    a = np.asarray(arr, dtype=float)
    if a.shape == shape:
        return a
    if a.ndim != 2 or len(shape) != 2:
        raise ValueError("align_field_to_shape expects a 2D array and shape (rows, cols)")
    from scipy.ndimage import zoom

    zr = shape[0] / a.shape[0]
    zc = shape[1] / a.shape[1]
    return zoom(a, (zr, zc), order=order)


def form_land_mask_connect(elev, edry=1):

    print("Forming connected land mask...")

    mask = label(elev>edry, background=1)
    prop = regionprops_table(
        mask, properties=["area", "label"])

    imax = np.argmax(prop["area"])
    
    land = np.zeros(mask.shape, dtype=np.uint8)
    land[mask == prop["label"][imax]] = 0
    land[mask != prop["label"][imax]] = 1

    return land


def setup_shoreline_pixels(hmat, land, hval):

    print("Computing shore adj. h(x)...")

    # Land pixels bordering ocean (legacy: only these received hshr — too narrow;
    # mesh vertices sit in water, so nearshore h(x) must also tag ocean cells.)
    epos = np.logical_and.reduce((
        land[+1:-1, +1:-1] >= 1, land[+1:-1, +2:] == 0))
    wpos = np.logical_and.reduce((
        land[+1:-1, +1:-1] >= 1, land[+1:-1, :-2] == 0))
    npos = np.logical_and.reduce((
        land[+1:-1, +1:-1] >= 1, land[:-2, +1:-1] == 0))
    spos = np.logical_and.reduce((
        land[+1:-1, +1:-1] >= 1, land[+2:, +1:-1] == 0))

    # Ocean pixels bordering land — same hval (hshr) so Jigsaw sees shore scale on the sea side
    epos_o = np.logical_and.reduce((
        land[+1:-1, +1:-1] == 0, land[+1:-1, +2:] >= 1))
    wpos_o = np.logical_and.reduce((
        land[+1:-1, +1:-1] == 0, land[+1:-1, :-2] >= 1))
    npos_o = np.logical_and.reduce((
        land[+1:-1, +1:-1] == 0, land[:-2, +1:-1] >= 1))
    spos_o = np.logical_and.reduce((
        land[+1:-1, +1:-1] == 0, land[+2:, +1:-1] >= 1))

    mask = np.full(hmat.shape, False, dtype=bool)
    mask[+1:-1, +1:-1] = np.logical_or.reduce(
        (npos, epos, spos, wpos, npos_o, epos_o, spos_o, wpos_o))

    hv = np.asarray(hval, dtype=hmat.dtype)
    hmat[mask] = hv

    return hmat


def coarsen_spacing_pixels(hmat, down):

    print("Coarsening mesh-spacing pixels...")

    rows = hmat.shape[0] // down
    cols = hmat.shape[1] // down

    htmp = np.full(
        (rows, cols), (np.amax(hmat)), dtype=hmat.dtype)

    for jpos in range(down):
        for ipos in range(down):

            iend = hmat.shape[0] - down + ipos + 1
            jend = hmat.shape[1] - down + jpos + 1

            htmp = np.minimum(
                htmp,
            hmat[ipos:iend:down, jpos:jend:down])

    return htmp


def filter_pixels_harmonic(hmat, exp=1):

    filt = remap_pixels_to_corner(hmat, exp)
    filt = remap_corner_to_pixels(filt, exp)

    return filt


def apply_deep_ocean_hmax_floor(
    hmat, elev, land, hmax_km: float, depth_m: float = -300.0
):
    """
    在足够深的开阔海域，保证 spacing（km）不低于用户设定的 hmax。

    swe_wavelength_spacing 在深水常给出约 20–40 km，且 hmat = min(hmax, wave) 会取更细的一侧，
    导致界面上的「深水尺度」调大后网格几乎不变。此处对深水像元做 max(h, hmax)，使 hmax
    真正成为深水区可达到的最粗尺度（仍受 Jigsaw marche 与 dhdx 平滑约束）。
    """
    if hmax_km <= 0:
        return hmat
    el = np.asarray(elev, dtype=float)
    ld = np.asarray(land, dtype=bool)
    oc = ~ld
    deep = oc & (el < float(depth_m))
    if not np.any(deep):
        return hmat
    out = np.asarray(hmat, dtype=np.float32, copy=True)
    out[deep] = np.maximum(out[deep].astype(np.float64), float(hmax_km)).astype(np.float32)
    return out


def repair_deep_ocean_spacing_after_harmonic(
    hmat, hmat_pre, elev, land, depth_m=-300.0
):
    """
    Harmonic smoothing uses np.minimum(..., filt); filt is dominated by small h near
    coast, so deep-ocean cells inherit overly fine spacing and hmax appears to
    "do nothing". For ocean deeper than depth_m (m, bathy negative), restore the
    floor from hmat_pre (field before smoothing).

    Apply again after remap_pixels_to_corner: corner averaging re-introduces the same
    coastal bleed into deep water, capping effective spacing at hmat*zoom well below hmax.
    """
    el = np.asarray(elev, dtype=float)
    oc = ~np.asarray(land, dtype=bool)
    deep = oc & (el < float(depth_m))
    if not np.any(deep):
        return hmat
    out = np.asarray(hmat, dtype=hmat.dtype, copy=True)
    pre = np.asarray(hmat_pre, dtype=hmat.dtype)
    out[deep] = np.maximum(out[deep], pre[deep])
    return out


def remap_pixels_to_corner(hmat, exp=1):

    R = hmat.shape[0]; C = hmat.shape[1]

    npos = np.arange(+0, hmat.shape[0] + 1)
    epos = np.arange(-1, hmat.shape[1] - 0)
    spos = np.arange(-1, hmat.shape[0] - 0)
    wpos = np.arange(+0, hmat.shape[1] + 1)
    
    npos[npos >= +R] = R - 1; spos[spos <= -1] = +0
    epos[epos <= -1] = C - 1; wpos[wpos >= +C] = +0

    npos, epos = np.meshgrid(
        npos, epos, sparse=True, indexing="ij")
    spos, wpos = np.meshgrid(
        spos, wpos, sparse=True, indexing="ij")

    htmp = (1. / hmat) ** exp
    hinv = htmp[npos, epos] + \
           htmp[npos, wpos] + \
           htmp[spos, epos] + \
           htmp[spos, wpos]

    return (4. / hinv) ** (1.0 / exp)


def remap_corner_to_pixels(hmat, exp=1):

    R = hmat.shape[0]; C = hmat.shape[1]

    npos = np.arange(+1, hmat.shape[0] + 0)
    epos = np.arange(+0, hmat.shape[1] - 1)
    spos = np.arange(+0, hmat.shape[0] - 1)
    wpos = np.arange(+1, hmat.shape[1] + 0)
    
    npos[npos >= +R] = R - 1; spos[spos <= -1] = +0
    epos[epos <= -1] = C - 1; wpos[wpos >= +C] = +0

    npos, epos = np.meshgrid(
        npos, epos, sparse=True, indexing="ij")
    spos, wpos = np.meshgrid(
        spos, wpos, sparse=True, indexing="ij")

    htmp = (1. / hmat) ** exp
    hinv = htmp[npos, epos] + \
           htmp[npos, wpos] + \
           htmp[spos, epos] + \
           htmp[spos, wpos]

    return (4. / hinv) ** (1.0 / exp)
    
    
def swe_wavelength_spacing(
        elev, land, nwav, hmin, hmax, grav=9.80665,
        T_M2=12.42*60.*60.):

    print("Computing wavelength heuristic...")

    vals = np.maximum(1, -elev)
    vals = T_M2 * (grav * vals) ** (1./2.) / nwav / 1000.

    vals[np.logical_and(elev >= -4., elev <= 4.)] = hmin

    vals = np.maximum(vals, hmin)
    vals = np.minimum(vals, hmax)

    vals = np.asarray(vals, dtype=np.float32)

    return vals


def elev_sharpness_spacing(
        xlon, ylat, 
        elev, dzdx, land, nslp, hmin, hmax, sdev):

    print("Computing GRAD(elev) heuristic...")

    dzdx = gaussian(np.asarray(
        dzdx, dtype=np.float32), sigma=sdev, mode="wrap")
   
    dzdx = np.maximum(1.E-08, dzdx) # no divide-by-zero

    vals = np.maximum(10, -elev) / dzdx / nslp / 1000.

    vals = np.maximum(vals, hmin)
    vals = np.minimum(vals, hmax)

    vals = np.asarray(vals, dtype=np.float32)
    
    return vals
   

def scale_spacing_via_mask(mask_file, vals):
    print("User-defined h(x) scaling...")
    if mask_file:
        data = nc.Dataset(mask_file, "r")
        vals = np.asarray(data["val"][:], dtype=np.float32)
    else:
        print("No mask file provided. Scaling will not be applied.")
    return vals

