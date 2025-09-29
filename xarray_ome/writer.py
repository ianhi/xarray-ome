"""Writing xarray DataTree and Dataset objects to OME-Zarr format."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    import xarray as xr


def write_ome_datatree(datatree: xr.DataTree, path: str | Path) -> None:
    """
    Write an xarray DataTree to OME-Zarr format.

    Parameters
    ----------
    datatree : xr.DataTree
        DataTree with multiscale pyramid structure to write
    path : str or Path
        Output path for the OME-Zarr store

    Notes
    -----
    Extracts OME-NGFF metadata from datatree attrs and converts xarray
    coordinates back to OME-NGFF coordinate transformations. Uses ngff-zarr
    for the actual writing.
    """
    raise NotImplementedError("Coming soon")


def write_ome_dataset(dataset: xr.Dataset, path: str | Path) -> None:
    """
    Write an xarray Dataset to OME-Zarr format as a single resolution level.

    Parameters
    ----------
    dataset : xr.Dataset
        Dataset to write
    path : str or Path
        Output path for the OME-Zarr store

    Notes
    -----
    Converts xarray coordinates to OME-NGFF coordinate transformations.
    Extracts OME-NGFF metadata from dataset attrs if present.
    """
    raise NotImplementedError("Coming soon")
