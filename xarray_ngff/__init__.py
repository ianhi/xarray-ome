"""xarray-ngff: OME integration for xarray."""

try:
    from ._version import __version__
except ImportError:
    __version__ = "unknown"

from . import accessor  # noqa: F401  (registers the ``.ngff`` accessor)
from .accessor import AxisInfo, ChannelInfo
from .reader import open_ngff_dataset, open_ngff_datatree
from .writer import write_ngff_dataset, write_ngff_datatree

__all__ = [
    "__version__",
    "AxisInfo",
    "ChannelInfo",
    "open_ngff_datatree",
    "open_ngff_dataset",
    "write_ngff_datatree",
    "write_ngff_dataset",
]
