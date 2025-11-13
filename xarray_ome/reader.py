"""Reading OME-Zarr files into xarray DataTree and Dataset objects."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import xarray as xr
from ngff_zarr import NgffImage, from_ngff_zarr  # type: ignore[import-untyped]

from ._store_utils import _detect_store_type
from .metadata import metadata_to_xarray_attrs
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

    Raises
    ------
    ValueError
        If the OME-Zarr store is not a simple multiscale image (e.g., HCS plate)

    Notes
    -----
    This function uses ngff-zarr to read the OME-Zarr store and parse metadata,
    then converts the multiscale structure to xarray with proper coordinates.

    Currently only supports simple multiscale images. HCS (High Content Screening)
    plate structures are not yet supported.
    """
    try:
        multiscales = from_ngff_zarr(str(path), validate=validate)
    except KeyError as e:
        if "multiscales" in str(e):
            store_type = _detect_store_type(str(path))
            if store_type == "hcs":
                msg = (
                    f"The OME-Zarr store at '{path}' appears to be an HCS (High Content "
                    "Screening) plate structure, which is not yet supported. "
                    "Currently only simple multiscale images are supported."
                )
                raise ValueError(msg) from e
            msg = (
                f"The OME-Zarr store at '{path}' does not contain multiscale metadata. "
                "It may be an unsupported OME-Zarr structure."
            )
            raise ValueError(msg) from e
        raise

    # Extract metadata dict for passing to conversion
    metadata_dict = _metadata_to_dict(multiscales.metadata)

    # Convert each scale level to a Dataset and create child nodes
    children = {}
    for i, ngff_image in enumerate(multiscales.images):
        dataset = _ngff_image_to_dataset(ngff_image, metadata_dict)
        scale_name = f"scale{i}"
        children[scale_name] = xr.DataTree(dataset, name=scale_name)

    # Create the root DataTree with children
    dt = xr.DataTree(children=children, name="root")

    # Add OME-NGFF metadata as attrs (coordinate-based metadata is in coords)
    metadata_attrs = metadata_to_xarray_attrs(metadata_dict)
    dt.attrs.update(metadata_attrs)

    return dt


def _extract_channel_labels(
    metadata: dict[str, Any] | None, expected_size: int | None = None
) -> list[str] | None:
    """Extract channel labels from OME-NGFF metadata.

    Handles metadata from all OME-NGFF versions (v0.1-v0.5).
    Channel labels are stored in omero.channels[].label.

    Parameters
    ----------
    metadata : dict, optional
        Full OME-NGFF metadata dict
    expected_size : int, optional
        Expected number of channels for validation

    Returns
    -------
    list of str or None
        Channel labels, or None if not available

    Notes
    -----
    The omero.channels metadata is marked as "transitional" in the spec
    but is the only standard location for channel labels in all versions.
    """
    if not metadata:
        return None

    omero = metadata.get("omero")
    if not omero:
        return None

    if not isinstance(omero, dict):
        return None

    channels = omero.get("channels", [])
    if not channels:
        return None

    channel_labels = []
    for i, ch in enumerate(channels):
        if isinstance(ch, dict):
            label = ch.get("label")
            if label:
                channel_labels.append(label)
            else:
                channel_labels.append(f"channel_{i}")
        else:
            channel_labels.append(f"channel_{i}")

    if expected_size is not None and len(channel_labels) != expected_size:
        return None

    return channel_labels if channel_labels else None


def _ngff_image_to_dataset(
    ngff_image: NgffImage, metadata: dict[str, Any] | None = None
) -> xr.Dataset:
    """Convert an NgffImage to an xarray Dataset.

    Parameters
    ----------
    ngff_image : NgffImage
        The image to convert
    metadata : dict, optional
        Full OME-NGFF metadata dict containing channel/time labels
    """
    # Get the data array
    data = ngff_image.data

    # Extract channel dimension size for validation
    channel_size = None
    if "c" in ngff_image.dims:
        channel_idx = ngff_image.dims.index("c")
        channel_size = data.shape[channel_idx]

    # Extract channel labels from OME metadata if available
    channel_labels = _extract_channel_labels(metadata, channel_size)

    # Could add time labels here in the future if spec is extended
    # For now, time is just numeric per OME-NGFF spec
    time_labels = None

    # Convert OME-NGFF transforms to xarray coordinates
    coords = transforms_to_coords(
        shape=data.shape,
        dims=ngff_image.dims,
        scale=ngff_image.scale,
        translation=ngff_image.translation,
        channel_labels=channel_labels,
        time_labels=time_labels,
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
    # These are needed for coords_to_transforms() to work efficiently
    dataset.attrs["ome_scale"] = ngff_image.scale
    dataset.attrs["ome_translation"] = ngff_image.translation

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

    Raises
    ------
    ValueError
        If the OME-Zarr store is not a simple multiscale image (e.g., HCS plate)

    Notes
    -----
    Coordinate transformations (scale/translation) from OME-NGFF are converted
    to explicit coordinate arrays in xarray.

    Currently only supports simple multiscale images. HCS (High Content Screening)
    plate structures are not yet supported.
    """
    try:
        multiscales = from_ngff_zarr(str(path), validate=validate)
    except KeyError as e:
        if "multiscales" in str(e):
            store_type = _detect_store_type(str(path))
            if store_type == "hcs":
                msg = (
                    f"The OME-Zarr store at '{path}' appears to be an HCS (High Content "
                    "Screening) plate structure, which is not yet supported. "
                    "Currently only simple multiscale images are supported."
                )
                raise ValueError(msg) from e
            msg = (
                f"The OME-Zarr store at '{path}' does not contain multiscale metadata. "
                "It may be an unsupported OME-Zarr structure."
            )
            raise ValueError(msg) from e
        raise

    # Extract metadata dict for passing to conversion
    metadata_dict = _metadata_to_dict(multiscales.metadata)

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
    dataset = _ngff_image_to_dataset(ngff_image, metadata_dict)

    # Store metadata about resolution level
    dataset.attrs["ome_ngff_resolution"] = resolution

    # Add OME-NGFF metadata as attrs (coordinate-based metadata is in coords)
    metadata_attrs = metadata_to_xarray_attrs(metadata_dict)
    dataset.attrs.update(metadata_attrs)

    return dataset
