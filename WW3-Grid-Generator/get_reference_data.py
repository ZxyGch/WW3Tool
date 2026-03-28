#!/usr/bin/env python3
"""
Download WW3-Grid-Generator/reference_data.

Default: GitHub Release asset tag ``data`` — fetch ``part_aa`` … ``part_ad``,
concatenate into ``reference_data.zip``, extract under WW3-Grid-Generator.

Optional ``--legacy``: fetch from original upstreams (NOAA GSHHS FTP, CEDA GEBCO
zip, dengwirda RTopo zip) — slower and more fragile, but does not rely on the
project’s split release archive.

If GitHub is slow or unreachable, you can obtain the same ``reference_data.zip``
manually from these mirrors, then extract so ``reference_data/`` exists (the
script prints its absolute path when run).

- **Ydray:** https://ydray.com/get/t/u17741446196277XguE91036edeefddAV
- **OneDrive:**
  https://tiangongeducn-my.sharepoint.com/:u:/r/personal/1911650207_tiangong_edu_cn/Documents/reference_data.zip?csf=1&web=1&e=SXDbA9
- **Baidu Netdisk:** https://pan.baidu.com/s/1SxQEfiaomdi3CXFOXC6DMw?pwd=cb48
  (extraction code: ``cb48``)
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

# Same ``reference_data.zip`` as the GitHub release bundle; for manual download if GitHub is slow.
REFERENCE_DATA_MIRROR_YDRAY = (
    "https://ydray.com/get/t/u17741446196277XguE91036edeefddAV"
)
REFERENCE_DATA_MIRROR_ONEDRIVE = (
    "https://tiangongeducn-my.sharepoint.com/:u:/r/personal/"
    "1911650207_tiangong_edu_cn/Documents/reference_data.zip?"
    "csf=1&web=1&e=SXDbA9"
)
REFERENCE_DATA_MIRROR_BAIDU = (
    "https://pan.baidu.com/s/1SxQEfiaomdi3CXFOXC6DMw?pwd=cb48"
)

_REFERENCE_DATA_DONE_BANNER = "=" * 70


def log_reference_data_download_complete(log=print) -> None:
    """Final banner after a successful run (GitHub bundle or ``--legacy``)."""
    w = len(_REFERENCE_DATA_DONE_BANNER)
    done_line = "reference_data download complete.".center(w)
    log("", flush=True)
    log(_REFERENCE_DATA_DONE_BANNER, flush=True)
    log(done_line, flush=True)
    log(_REFERENCE_DATA_DONE_BANNER, flush=True)


def print_reference_data_mirror_help(
    log=print,
    ref_dir: Path | str | None = None,
) -> None:
    """Print alternate download locations (English)."""
    if ref_dir is not None:
        target = Path(ref_dir).expanduser().resolve()
    else:
        target = (Path(__file__).resolve().parent / "reference_data").resolve()
    log("", flush=True)
    log(
        "If GitHub is slow or unreachable, obtain the same reference_data.zip from:",
        flush=True,
    )
    log(f"  Ydray:        {REFERENCE_DATA_MIRROR_YDRAY}", flush=True)
    log("", flush=True)
    log(f"  OneDrive:     {REFERENCE_DATA_MIRROR_ONEDRIVE}", flush=True)
    log("", flush=True)
    log(f"  Baidu Netdisk: {REFERENCE_DATA_MIRROR_BAIDU}", flush=True)
    log("", flush=True)

    log(
        "Then extract so the reference_data directory exists at this absolute path:",
        flush=True,
    )
    log(f"  {target}", flush=True)
    log("", flush=True)
    log("", flush=True)


def _reporthook(
    block_num: int,
    block_size: int,
    total_size: int,
    name: str = "",
    log=print,
) -> None:
    """Progress callback for urlretrieve; prints ~every 5% when Content-Length is known (plus start & 100%)."""
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
    # Do not use ``pct >= 99.5``: urlretrieve calls this for every block, so that would spam identical lines.
    if (
        block_num == 0
        or downloaded >= total_size
        or int(pct // 5) > int(prev_pct // 5)
    ):
        log(
            f"  [{name}] Progress: {pct:.1f}% ({mb_d:.1f} / {mb_t:.1f} MB)",
            flush=True,
        )


def _zip_normalized_roots(namelist: list[str]) -> set[str]:
    """Top-level path components in the archive, ignoring ``__MACOSX`` and dot junk."""
    roots: set[str] = set()
    for raw in namelist:
        n = raw.replace("\\", "/").strip()
        if not n or n.endswith("/"):
            continue
        first = n.split("/")[0]
        if first == "__MACOSX" or first.startswith("."):
            continue
        roots.add(first)
    return roots


def flatten_nested_reference_data_dir(ref_dir: Path, log=print) -> None:
    """
    If data ended up as ``reference_data/reference_data/...`` (wrong extract target
    or odd zip layout), move inner contents up to ``ref_dir``.
    """
    inner = ref_dir / "reference_data"
    if not inner.is_dir():
        return
    log("Fixing nested reference_data/reference_data (moving inner files up)…", flush=True)
    for item in list(inner.iterdir()):
        dest = ref_dir / item.name
        if dest.exists():
            if dest.is_dir() and item.is_dir():
                for sub in list(item.iterdir()):
                    shutil.move(str(sub), str(dest / sub.name))
                try:
                    item.rmdir()
                except OSError:
                    shutil.rmtree(item)
            else:
                if dest.is_dir():
                    shutil.rmtree(dest)
                else:
                    dest.unlink()
                shutil.move(str(item), str(dest))
        else:
            shutil.move(str(item), str(dest))
    try:
        inner.rmdir()
    except OSError:
        pass


def download(url: str, dest: Path, name: str = "", log=print) -> None:
    """Stream ``url`` to ``dest`` with progress via ``_reporthook``."""
    name = name or dest.name
    log(f"Downloading: {name}", flush=True)
    log(f"  URL: {url}", flush=True)
    log("", flush=True)
    urlretrieve(url, dest.as_posix(), lambda b, bs, ts: _reporthook(b, bs, ts, name, log))
    log("", flush=True)


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

    release_page = "https://github.com/ZxyGch/WW3Tool/releases/tag/data"
    log(
        "Downloading reference_data split parts from GitHub WW3Tool Release `data`…",
        flush=True,
    )
    log(f"  Release page: {release_page}", flush=True)
    log("", flush=True)

    for url, pname in zip(REFERENCE_DATA_PART_URLS, REFERENCE_DATA_PART_NAMES):
        dest_part = work_dir / pname
        download(url, dest_part, pname, log=log)

    log("", flush=True)
    log("Merging parts into reference_data.zip…", flush=True)
    with zip_path.open("wb") as out_zip:
        for pname in REFERENCE_DATA_PART_NAMES:
            part_path = work_dir / pname
            if not part_path.is_file() or part_path.stat().st_size == 0:
                raise OSError(f"Split part missing or empty: {pname}")
            with part_path.open("rb") as inf:
                shutil.copyfileobj(inf, out_zip)

    log("", flush=True)
    log("Extracting to reference_data…", flush=True)
    ref_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        names = zf.namelist()
        file_members = [n for n in names if n.strip() and not n.endswith("/")]
        if not file_members:
            raise OSError("No valid files in reference_data.zip")
        top_roots = _zip_normalized_roots(names)
        if len(top_roots) == 1 and next(iter(top_roots)).lower() == "reference_data":
            # Layout: reference_data/coastal_bound_....mat → work_dir/reference_data/
            zf.extractall(work_dir)
        else:
            # Flat archive: drop files straight into ref_dir
            zf.extractall(ref_dir)
        flatten_nested_reference_data_dir(ref_dir, log=log)

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

    log("", flush=True)
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
    parser.add_argument(
        "--ref-dir",
        type=Path,
        default=None,
        metavar="DIR",
        help=(
            "Directory to receive reference_data files (default: <WW3-Grid-Generator>/reference_data). "
            "Split parts and reference_data.zip are written under DIR's parent."
        ),
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parent
    if args.ref_dir is not None:
        ref_dir = Path(args.ref_dir).expanduser().resolve()
        work_dir = ref_dir.parent
    else:
        ref_dir = root / "reference_data"
        work_dir = root

    print_reference_data_mirror_help(ref_dir=ref_dir)

    if args.legacy:
        main_legacy(root, ref_dir)
    else:
        download_reference_data_github(work_dir, ref_dir)

    log_reference_data_download_complete()


if __name__ == "__main__":
    main()
