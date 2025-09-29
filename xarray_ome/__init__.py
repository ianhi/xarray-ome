"""xarray-ome: OME integration for xarray."""

try:
    from ._version import __version__
except ImportError:
    __version__ = "unknown"

from .reader import open_ome_dataset, open_ome_datatree
from .writer import write_ome_dataset, write_ome_datatree

__all__ = [
    "__version__",
    "open_ome_datatree",
    "open_ome_dataset",
    "write_ome_datatree",
    "write_ome_dataset",
]
