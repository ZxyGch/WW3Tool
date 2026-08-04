"""setuptools 布局配置。

run.py 位于仓库根（py-module `run`），而源码包 workflows/、desktop/
位于 src/ 下 —— 用显式 package_dir 映射，使二者都能打进 wheel。
其余元数据（依赖、console script）见 pyproject.toml。
"""
from setuptools import find_packages, setup

setup(
    py_modules=["run"],
    package_dir={"workflows": "src/workflows", "desktop": "src/desktop"},
    packages=find_packages("src"),
)
