
import os
import platform
import subprocess
import shutil
import argparse

HERE = os.path.abspath(os.path.dirname(__file__))


def _running_under_rosetta():
    """True if this process is x86_64-on-ARM via Rosetta (Apple Silicon)."""
    if platform.system() != "Darwin":
        return False
    try:
        out = subprocess.check_output(
            ["sysctl", "-n", "sysctl.proc_translated"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        return out == "1"
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return False


def _darwin_cmake_extras(netcdf_user_path):
    """
    - Native arm64: single-arch arm64 build (matches /opt/homebrew).
    - Rosetta x86_64 Python: single-arch x86_64 and ignore /opt/homebrew so CMake
      does not pick arm64-only Homebrew NetCDF (undefined symbols for x86_64).
      Use conda-forge libnetcdf in that env if you need NetCDF.
    """
    if platform.system() != "Darwin":
        return []
    extras = []
    if _running_under_rosetta():
        if netcdf_user_path and str(netcdf_user_path).startswith("/opt/homebrew"):
            print(
                "WARNING: --netcdf-user-path under /opt/homebrew with x86_64 Python "
                "(Rosetta): use arm64 Miniconda, or conda x86_64 NetCDF, or omit.",
                flush=True,
            )
        print(
            "NOTE: Rosetta build: ignoring /opt/homebrew for CMake search; "
            "install matching-arch NetCDF (e.g. conda install -c conda-forge libnetcdf).",
            flush=True,
            )
        extras.append("-DCMAKE_IGNORE_PREFIX_PATH=/opt/homebrew")
        extras.append("-DCMAKE_OSX_ARCHITECTURES=x86_64")
    elif platform.machine() == "arm64":
        extras.append("-DCMAKE_OSX_ARCHITECTURES=arm64")
    return extras


def _cmake_env():
    """Strip ARCHFLAGS on macOS so CMake/arch flags are not contradicted."""
    env = os.environ.copy()
    if platform.system() == "Darwin":
        env.pop("ARCHFLAGS", None)
    return env


def build_external(build_type="Release",
                   netcdf_user_path=None,
                   openmp_user_path=None
                   ):
#-- The actual cmake-based build steps for JIGSAW

    cwd_pointer = os.getcwd()

    try:
        print("cmake config. for jigsaw...")

        source_path = os.path.join(
            HERE, "external", "jigsaw")

        builds_path = \
            os.path.join(source_path, "tmp")

        install_prefix = os.path.join(source_path, "_cmake_install")

        shutil.rmtree(builds_path, ignore_errors=True)
        shutil.rmtree(install_prefix, ignore_errors=True)
        os.makedirs(builds_path, exist_ok=True)

        exesrc_path = os.path.join(install_prefix, "bin")
        libsrc_path = os.path.join(install_prefix, "lib")

        exedst_path = os.path.join(
            HERE, "jigsawpy", "_bin")

        libdst_path = os.path.join(
            HERE, "jigsawpy", "_lib")

        shutil.rmtree(
            exedst_path, ignore_errors=True)
        shutil.rmtree(
            libdst_path, ignore_errors=True)

        os.chdir(builds_path)

        config_call = [
            "cmake", "..",
            "-DCMAKE_BUILD_TYPE=" + build_type,
            "-DCMAKE_INSTALL_PREFIX=" + install_prefix,
        ]
        config_call += _darwin_cmake_extras(netcdf_user_path)

        if (netcdf_user_path is not None):
            config_call+= [
        "-DNETCDF_USER_PATH="+netcdf_user_path]

        if (openmp_user_path is not None):
            config_call+= [
        "-DOPENMP_USER_PATH="+openmp_user_path]

        print(config_call)
        cmake_env = _cmake_env()
        subprocess.run(config_call, check=True, env=cmake_env)

        print("cmake compile for jigsaw...")

        try:
            compilecall = [
                "cmake", "--build", ".",
                "--config", build_type,
                "--target", "install",
                "--parallel", "4"
                ]
            subprocess.run(
                compilecall, check=True, env=cmake_env)

        except subprocess.CalledProcessError:
            compilecall = [
                "cmake", "--build", ".",
                "--config", build_type,
                "--target", "install"
                ]
            subprocess.run(
                compilecall, check=True, env=cmake_env)

        print("cmake cleanup for jigsaw...")

        shutil.copytree(exesrc_path, exedst_path)
        shutil.copytree(libsrc_path, libdst_path)

    finally:
        os.chdir(cwd_pointer)

        shutil.rmtree(builds_path, ignore_errors=True)
        shutil.rmtree(
            os.path.join(HERE, "external", "jigsaw", "_cmake_install"),
            ignore_errors=True)


if (__name__ == "__main__"):
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawTextHelpFormatter)

    parser.add_argument(
        "--cmake-build-type", dest="cmake_build_type",
        required=False,
        type=str, default="Release",
        help="Build JIGSAW in {Release}, Debug mode.")

    parser.add_argument(
        "--netcdf-user-path", dest="netcdf_user_path",
        required=False,
        type=str, default=None,
        help="(Optional) dir. containing netcdf lib.")

    parser.add_argument(
        "--openmp-user-path", dest="openmp_user_path",
        required=False,
        type=str, default=None,
        help="(Optional) dir. containing openmp lib.")

    args = parser.parse_args()

    build_external(args.cmake_build_type,
                   args.netcdf_user_path,
                   args.openmp_user_path)
