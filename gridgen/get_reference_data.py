#!/usr/bin/env python3

import os
import tarfile
import zipfile
from pathlib import Path
from urllib.request import urlretrieve


GSHHS_URL = "ftp://polar.ncep.noaa.gov/waves/gridgen/gridgen_addit.tar.gz"
GEBCO_URL = "https://dap.ceda.ac.uk/bodc/gebco/global/gebco_2025/sub_ice_topography_bathymetry/netcdf/gebco_2025_sub_ice_topo.zip"


def download(url: str, dest: Path) -> None:
    print(f"Downloading: {url}")
    urlretrieve(url, dest.as_posix())


def main() -> None:
    root = Path(__file__).resolve().parent
    ref_dir = root / "reference_data"
    ref_dir.mkdir(parents=True, exist_ok=True)

    gshhs_archive = root / "gridgen_addit.tar.gz"
    gebco_archive = root / "gebco_2025_sub_ice_topo.zip"

    # Download GSHHS coastline data
    download(GSHHS_URL, gshhs_archive)

    # Extract GSHHS
    print("Extracting GSHHS coastline data...")
    with tarfile.open(gshhs_archive, "r:gz") as tar:
        tar.extractall(ref_dir)

    # Download GEBCO 2025 bathymetry data
    download(GEBCO_URL, gebco_archive)

    # Extract GEBCO
    print("Extracting GEBCO data...")
    with zipfile.ZipFile(gebco_archive, "r") as zf:
        zf.extractall(ref_dir)

    # Rename GEBCO file if present
    src = ref_dir / "gebco_2025_sub_ice_topo.nc"
    dst = ref_dir / "gebco.nc"
    if src.exists():
        src.replace(dst)
        print("Renamed GEBCO file to gebco.nc")

    print("Reference data download complete.")
    print(f"Please check: {ref_dir}")


if __name__ == "__main__":
    main()

