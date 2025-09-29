"""Reading OME-Zarr files into xarray DataTree and Dataset objects."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import xarray as xr
from ngff_zarr import NgffImage, from_ngff_zarr

from .transforms import transforms_to_coords

if TYPE_CHECKING:
    from pathlib import Path


def open_ome_datatree(path: str | Path, validate: bool = False) -> xr.DataTree:
    """
    Open an OME-Zarr store as an xarray DataTree.

    Parameters
    ----------
    path : str or Path
        Path to the OME-Zarr store (local directory or URL)
    validate : bool, default=False
        Whether to validate metadata against OME-NGFF specification

    Returns
    -------
    xr.DataTree
        DataTree with multiscale pyramid structure. Each resolution level
        is stored as a child node. OME-NGFF metadata is preserved in attrs.

    Notes
    -----
    This function uses ngff-zarr to read the OME-Zarr store and parse metadata,
    then converts the multiscale structure to xarray with proper coordinates.
    """
    # Use ngff-zarr to read the store
    multiscales = from_ngff_zarr(str(path), validate=validate)

    # Create the root DataTree node
    dt = xr.DataTree(name="root")

    # Store the full OME-NGFF metadata in root attrs
    # Convert metadata to dict for serialization
    dt.attrs["ome_ngff_metadata"] = _metadata_to_dict(multiscales.metadata)

    # Convert each scale level to a Dataset and add as child node
    for i, ngff_image in enumerate(multiscales.images):
        dataset = _ngff_image_to_dataset(ngff_image)
        # Create child node with scale level name
        scale_name = f"scale{i}"
        xr.DataTree(dataset, name=scale_name, parent=dt)

    return dt


def _ngff_image_to_dataset(ngff_image: NgffImage) -> xr.Dataset:
    """Convert an NgffImage to an xarray Dataset."""
    # Get the data array
    data = ngff_image.data

    # Convert OME-NGFF transforms to xarray coordinates
    coords = transforms_to_coords(
        shape=data.shape,
        dims=ngff_image.dims,
        scale=ngff_image.scale,
        translation=ngff_image.translation,
    )

    # Create DataArray with coordinates
    data_array = xr.DataArray(
        data,
        dims=ngff_image.dims,
        coords=coords,
        name=ngff_image.name,
    )

    # Create Dataset
    dataset = xr.Dataset({ngff_image.name: data_array})

    # Store scale and translation in attrs for round-tripping
    dataset.attrs["ome_scale"] = ngff_image.scale
    dataset.attrs["ome_translation"] = ngff_image.translation
    if ngff_image.axes_units:
        dataset.attrs["ome_axes_units"] = dict(ngff_image.axes_units)
    if ngff_image.axes_orientations:
        dataset.attrs["ome_axes_orientations"] = {
            k: str(v) for k, v in ngff_image.axes_orientations.items()
        }

    return dataset


def _metadata_to_dict(metadata: Any) -> dict[str, Any]:
    """Convert OME-NGFF metadata to a dictionary."""
    # For now, use dataclass conversion
    # This preserves the metadata for round-tripping
    from dataclasses import asdict

    return asdict(metadata)


def open_ome_dataset(path: str | Path, resolution: int = 0, validate: bool = False) -> xr.Dataset:
    """
    Open a single resolution level from an OME-Zarr store as an xarray Dataset.

    Parameters
    ----------
    path : str or Path
        Path to the OME-Zarr store (local directory or URL)
    resolution : int, default=0
        Which resolution level to open (0 is highest resolution)
    validate : bool, default=False
        Whether to validate metadata against OME-NGFF specification

    Returns
    -------
    xr.Dataset
        Dataset with proper physical coordinates derived from OME-NGFF
        coordinate transformations. OME-NGFF metadata is preserved in attrs.

    Notes
    -----
    Coordinate transformations (scale/translation) from OME-NGFF are converted
    to explicit coordinate arrays in xarray.
    """
    # Use ngff-zarr to read the store
    multiscales = from_ngff_zarr(str(path), validate=validate)

    # Check that resolution level exists
    if resolution >= len(multiscales.images):
        msg = (
            f"Resolution level {resolution} not found. "
            f"Available levels: 0-{len(multiscales.images) - 1}"
        )
        raise ValueError(msg)

    # Get the requested resolution level
    ngff_image = multiscales.images[resolution]

    # Convert to Dataset
    dataset = _ngff_image_to_dataset(ngff_image)

    # Store metadata about resolution level
    dataset.attrs["ome_ngff_resolution"] = resolution
    dataset.attrs["ome_ngff_metadata"] = _metadata_to_dict(multiscales.metadata)

    return dataset
