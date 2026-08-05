"""WW3Tool runtime resources (pip install layout).

Build-time staged resources (params.yml / public / meshgen / requirements).
"""

from pathlib import Path

__all__ = ["resource_root", "is_packaged_root"]


def resource_root() -> Path:
    """Return this resource package's root directory."""
    return Path(__file__).resolve().parent


def is_packaged_root() -> bool:
    """True when this package carries the staged resources."""
    return (Path(__file__).resolve().parent / "params.yml").is_file()
