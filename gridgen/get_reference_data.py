#!/usr/bin/env python3

import tarfile
import zipfile
from pathlib import Path
from urllib.request import urlretrieve


GSHHS_URL = "ftp://polar.ncep.noaa.gov/waves/gridgen/gridgen_addit.tar.gz"
GEBCO_URL = "https://dap.ceda.ac.uk/bodc/gebco/global/gebco_2025/sub_ice_topography_bathymetry/netcdf/gebco_2025_sub_ice_topo.zip"
# RTopo + GEBCO 混合 DEM（约 60″），供 unst_msh_gen 等非结构网格使用；来源：dengwirda/dem releases
RTOPO_ZIP_URL = (
    "https://github.com/dengwirda/dem/releases/download/v0.1.1/"
    "RTopo_2_0_4_GEBCO_v2023_60sec_pixel.zip"
)


def _reporthook(block_num: int, block_size: int, total_size: int, name: str = "") -> None:
    """下载进度回调：按百分比或已下载量打印，并 flush 以便实时显示。"""
    downloaded = block_num * block_size
    if total_size <= 0:
        if block_num % 200 == 0 or block_num < 3:
            mb = downloaded / (1024 * 1024)
            print(f"  [{name}] 已下载: {mb:.1f} MB", flush=True)
        return
    downloaded = min(downloaded, total_size)
    pct = 100.0 * downloaded / total_size
    mb_d = downloaded / (1024 * 1024)
    mb_t = total_size / (1024 * 1024)
    # 每 5% 打印一次，首尾必打
    prev_pct = (block_num - 1) * block_size * 100.0 / total_size if block_num else 0
    if block_num == 0 or pct >= 99.5 or int(pct // 5) > int(prev_pct // 5):
        print(f"  [{name}] 进度: {pct:.1f}% ({mb_d:.1f} / {mb_t:.1f} MB)", flush=True)


def download(url: str, dest: Path, name: str = "") -> None:
    name = name or dest.name
    print(f"Downloading: {name}", flush=True)
    urlretrieve(url, dest.as_posix(), lambda b, bs, ts: _reporthook(b, bs, ts, name))


def main() -> None:
    root = Path(__file__).resolve().parent
    ref_dir = root / "reference_data"
    ref_dir.mkdir(parents=True, exist_ok=True)

    gshhs_archive = root / "gridgen_addit.tar.gz"
    gebco_archive = root / "gebco_2025_sub_ice_topo.zip"
    rtopo_archive = root / "RTopo_2_0_4_GEBCO_v2023_60sec_pixel.zip"

    # Download GSHHS coastline data
    print("Step 1/6: 下载 GSHHS 海岸线数据...", flush=True)
    download(GSHHS_URL, gshhs_archive, "gridgen_addit.tar.gz")

    # Extract GSHHS
    print("Step 2/6: 解压 GSHHS 海岸线数据...", flush=True)
    with tarfile.open(gshhs_archive, "r:gz") as tar:
        tar.extractall(ref_dir)
    print("  GSHHS 解压完成", flush=True)

    # Download GEBCO 2025 bathymetry data
    print("Step 3/6: 下载 GEBCO 水深数据...", flush=True)
    download(GEBCO_URL, gebco_archive, "gebco_2025_sub_ice_topo.zip")

    # Extract GEBCO
    print("Step 4/6: 解压 GEBCO 并重命名...", flush=True)
    with zipfile.ZipFile(gebco_archive, "r") as zf:
        zf.extractall(ref_dir)
    src = ref_dir / "gebco_2025_sub_ice_topo.nc"
    dst = ref_dir / "gebco.nc"
    if src.exists():
        src.replace(dst)
        print("  已重命名为 gebco.nc", flush=True)

    # Download RTopo DEM (for unstructured mesh / WW3Tool unst_msh_gen)
    print("Step 5/6: 下载 RTopo DEM (RTopo_2_0_4_GEBCO_v2023_60sec_pixel)...", flush=True)
    download(RTOPO_ZIP_URL, rtopo_archive, "RTopo_2_0_4_GEBCO_v2023_60sec_pixel.zip")

    print("Step 6/6: 解压 RTopo DEM 到 reference_data...", flush=True)
    with zipfile.ZipFile(rtopo_archive, "r") as zf:
        zf.extractall(ref_dir)
    print("  RTopo 解压完成", flush=True)

    print("Reference data 下载与解压全部完成。", flush=True)
    print(f"路径: {ref_dir}", flush=True)


if __name__ == "__main__":
    main()

