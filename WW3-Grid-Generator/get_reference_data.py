#!/usr/bin/env python3
"""
Download WW3-Grid-Generator/reference_data.

Default: GitHub Release asset tag ``data`` — fetch ``part_aa`` … ``part_ad``,
concatenate into ``reference_data.zip``, extract under WW3-Grid-Generator.

Optional ``--legacy``: fetch from original upstreams (NOAA GSHHS FTP, CEDA GEBCO
zip, dengwirda RTopo zip) — slower and more fragile, but does not rely on the
project’s split release archive.
"""

from __future__ import annotations

import argparse
import shutil
import tarfile
import zipfile
from pathlib import Path
from urllib.request import urlretrieve

# WW3Tool GitHub release bundle (tag: data)
REFERENCE_DATA_PART_URLS = [
    "https://github.com/ZxyGch/WW3Tool/releases/download/data/part_aa",
    "https://github.com/ZxyGch/WW3Tool/releases/download/data/part_ab",
    "https://github.com/ZxyGch/WW3Tool/releases/download/data/part_ac",
    "https://github.com/ZxyGch/WW3Tool/releases/download/data/part_ad",
]
REFERENCE_DATA_PART_NAMES = ["part_aa", "part_ab", "part_ac", "part_ad"]

# --legacy only: NOAA WW3 toolkit add-on (coastal_bound*.mat, optional polygons, …)
GSHHS_URL = "ftp://polar.ncep.noaa.gov/waves/gridgen/gridgen_addit.tar.gz"
# --legacy only: full GEBCO 2025 sub-ice NetCDF inside zip; renamed to gebco.nc after extract
GEBCO_URL = (
    "https://dap.ceda.ac.uk/bodc/gebco/global/gebco_2025/"
    "sub_ice_topography_bathymetry/netcdf/gebco_2025_sub_ice_topo.zip"
)
# --legacy only: RTopo blend for unst_msh_gen-style workflows
RTOPO_ZIP_URL = (
    "https://github.com/dengwirda/dem/releases/download/v0.1.1/"
    "RTopo_2_0_4_GEBCO_v2023_60sec_pixel.zip"
)


def _reporthook(
    block_num: int,
    block_size: int,
    total_size: int,
    name: str = "",
    log=print,
) -> None:
    """Progress callback for urlretrieve; prints MB or percent every ~5% when size is known."""
    downloaded = block_num * block_size
    if total_size <= 0:
        # Server did not send Content-Length: print sparse MB updates only
        if block_num % 200 == 0 or block_num < 3:
            mb = downloaded / (1024 * 1024)
            log(f"  [{name}] Downloaded: {mb:.1f} MB", flush=True)
        return
    downloaded = min(downloaded, total_size)
    pct = 100.0 * downloaded / total_size
    mb_d = downloaded / (1024 * 1024)
    mb_t = total_size / (1024 * 1024)
    prev_pct = (block_num - 1) * block_size * 100.0 / total_size if block_num else 0
    if block_num == 0 or pct >= 99.5 or int(pct // 5) > int(prev_pct // 5):
        log(
            f"  [{name}] Progress: {pct:.1f}% ({mb_d:.1f} / {mb_t:.1f} MB)",
            flush=True,
        )


def download(url: str, dest: Path, name: str = "", log=print) -> None:
    """Stream ``url`` to ``dest`` with progress via ``_reporthook``."""
    name = name or dest.name
    log(f"Downloading: {name}", flush=True)
    urlretrieve(url, dest.as_posix(), lambda b, bs, ts: _reporthook(b, bs, ts, name, log))


def download_reference_data_github(
    work_dir: Path,
    ref_dir: Path,
    *,
    log=print,
) -> None:
    """
    Download the split release archive from GitHub, merge, and extract.

    1. Download split parts into ``work_dir``.
    2. Binary-concatenate to ``reference_data.zip`` (order: aa, ab, ac, ad).
    3. Extract: if the zip has a single top-level folder ``reference_data/``,
       extract under ``work_dir`` so ``work_dir/reference_data/...`` exists;
       otherwise extract directly into ``ref_dir``.

    Args:
        work_dir: WW3-Grid-Generator root (parent of ``reference_data``); temp parts + zip live here.
        ref_dir: Target ``.../reference_data`` directory (used for flat zips).
        log: Callable for progress messages (default ``print``).
    """
    work_dir.mkdir(parents=True, exist_ok=True)
    zip_path = work_dir / "reference_data.zip"

    log(
        "Downloading reference_data split parts from GitHub WW3Tool Release `data`…",
        flush=True,
    )

    for url, pname in zip(REFERENCE_DATA_PART_URLS, REFERENCE_DATA_PART_NAMES):
        dest_part = work_dir / pname
        log(f"Downloading part: {pname}", flush=True)
        download(url, dest_part, pname, log=log)

    log("Merging parts into reference_data.zip…", flush=True)
    with zip_path.open("wb") as out_zip:
        for pname in REFERENCE_DATA_PART_NAMES:
            part_path = work_dir / pname
            if not part_path.is_file() or part_path.stat().st_size == 0:
                raise OSError(f"Split part missing or empty: {pname}")
            with part_path.open("rb") as inf:
                shutil.copyfileobj(inf, out_zip)

    log("Extracting to reference_data…", flush=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        file_members = [n for n in zf.namelist() if n.strip() and not n.endswith("/")]
        if not file_members:
            raise OSError("No valid files in reference_data.zip")
        top_roots = {n.split("/")[0] for n in file_members}
        if len(top_roots) == 1 and next(iter(top_roots)) == "reference_data":
            # Layout: reference_data/coastal_bound_....mat → work_dir/reference_data/
            zf.extractall(work_dir)
        else:
            # Flat archive: drop files straight into ref_dir
            ref_dir.mkdir(parents=True, exist_ok=True)
            zf.extractall(ref_dir)

    # Remove split parts and merged zip to save disk space
    for pname in REFERENCE_DATA_PART_NAMES:
        try:
            (work_dir / pname).unlink()
        except OSError:
            pass
    try:
        zip_path.unlink()
    except OSError:
        pass

    log("GitHub reference_data download and extraction finished.", flush=True)
    log(f"Path: {ref_dir}", flush=True)


def main_legacy(root: Path, ref_dir: Path, log=print) -> None:
    """
    ``--legacy`` mode: download GSHHS, GEBCO, RTopo from upstream URLs (no GitHub bundle).

    Large archives are written next to this script under ``root``; extracted content
    goes under ``ref_dir``. GEBCO NetCDF is renamed to ``gebco.nc`` for WW3Tool expectations.
    """
    gshhs_archive = root / "gridgen_addit.tar.gz"
    gebco_archive = root / "gebco_2025_sub_ice_topo.zip"
    rtopo_archive = root / "RTopo_2_0_4_GEBCO_v2023_60sec_pixel.zip"
    ref_dir.mkdir(parents=True, exist_ok=True)

    log("Step 1/6: Downloading GSHHS coastline data…", flush=True)
    download(GSHHS_URL, gshhs_archive, "gridgen_addit.tar.gz", log=log)

    log("Step 2/6: Extracting GSHHS into reference_data…", flush=True)
    with tarfile.open(gshhs_archive, "r:gz") as tar:
        tar.extractall(ref_dir)
    log("  GSHHS extraction done.", flush=True)

    log("Step 3/6: Downloading GEBCO bathymetry…", flush=True)
    download(GEBCO_URL, gebco_archive, "gebco_2025_sub_ice_topo.zip", log=log)

    log("Step 4/6: Extracting GEBCO and renaming…", flush=True)
    with zipfile.ZipFile(gebco_archive, "r") as zf:
        zf.extractall(ref_dir)
    src = ref_dir / "gebco_2025_sub_ice_topo.nc"
    dst = ref_dir / "gebco.nc"
    if src.exists():
        src.replace(dst)
        log("  Renamed to gebco.nc", flush=True)

    log("Step 5/6: Downloading RTopo DEM…", flush=True)
    download(RTOPO_ZIP_URL, rtopo_archive, "RTopo_2_0_4_GEBCO_v2023_60sec_pixel.zip", log=log)

    log("Step 6/6: Extracting RTopo DEM into reference_data…", flush=True)
    with zipfile.ZipFile(rtopo_archive, "r") as zf:
        zf.extractall(ref_dir)
    log("  RTopo extraction done.", flush=True)

    log("(--legacy) Upstream multi-source download and extraction finished.", flush=True)
    log(f"Path: {ref_dir}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch WW3-Grid-Generator/reference_data (default: GitHub WW3Tool release bundle)."
    )
    parser.add_argument(
        "--legacy",
        action="store_true",
        help="Use original multi-source download (NOAA GSHHS FTP, CEDA GEBCO, GitHub dengwirda RTopo) instead of GitHub bundle.",
    )
    args = parser.parse_args()

    # Script lives in WW3-Grid-Generator/; reference_data is the standard subfolder
    root = Path(__file__).resolve().parent
    ref_dir = root / "reference_data"

    if args.legacy:
        main_legacy(root, ref_dir)
    else:
        download_reference_data_github(root, ref_dir)


if __name__ == "__main__":
    main()
