"""Coordinate transformation utilities for OME-NGFF <-> xarray conversion."""

from __future__ import annotations

from typing import TYPE_CHECKING, Hashable, Sequence

import numpy as np

if TYPE_CHECKING:
    import xarray as xr


def transforms_to_coords(
    shape: tuple[int, ...],
    dims: Sequence[str],
    scale: dict[str, float],
    translation: dict[str, float],
    *,
    channel_labels: list[str] | None = None,
    time_labels: list[str] | None = None,
) -> dict[str, np.ndarray]:
    """
    Convert OME-NGFF coordinate transformations to xarray coordinate arrays.

    Parameters
    ----------
    shape : tuple of int
        Array shape
    dims : sequence of str
        Dimension names (e.g., ['t', 'c', 'z', 'y', 'x'])
    scale : dict[str, float]
        Scale factors for each dimension
    translation : dict[str, float]
        Translation offsets for each dimension
    channel_labels : list of str, optional
        Channel names from OME metadata (omero.channels[].label)
    time_labels : list of str, optional
        Time point labels from OME metadata

    Returns
    -------
    dict[str, np.ndarray]
        Mapping of dimension names to coordinate arrays

    Notes
    -----
    Implements the logic for converting OME-NGFF scale/translation transforms
    to explicit coordinate arrays.

    For each dimension, the coordinate array is computed as:
        coords[dim] = translation[dim] + scale[dim] * np.arange(size[dim])

    For channel and time dimensions, if labels are provided, they are used
    instead of numeric indices to create more meaningful coordinate arrays.

    This represents physical/world coordinates rather than pixel indices.

    References
    ----------
    https://github.com/JaneliaSciComp/xarray-ome-ngff/blob/main/src/xarray_ome_ngff/v04/multiscale.py#L118-L123
    """
    coords: dict[str, np.ndarray] = {}

    for dim, size in zip(dims, shape):
        # Special handling for channel dimension with labels
        if dim == "c" and channel_labels is not None and len(channel_labels) == size:
            coords[dim] = np.array(channel_labels, dtype=str)
        # Special handling for time dimension with labels
        elif dim == "t" and time_labels is not None and len(time_labels) == size:
            coords[dim] = np.array(time_labels, dtype=str)
        else:
            # Get scale and translation for this dimension
            dim_scale = scale.get(dim, 1.0)
            dim_translation = translation.get(dim, 0.0)

            # Create coordinate array: translation + scale * indices
            # This converts pixel indices to physical coordinates
            coords[dim] = dim_translation + dim_scale * np.arange(size)

    return coords


def coords_to_transforms(
    dataset: xr.Dataset,
) -> tuple[dict[Hashable, float], dict[Hashable, float]]:
    """
    Convert xarray coordinates back to OME-NGFF coordinate transformations.

    Parameters
    ----------
    dataset : xr.Dataset
        Dataset with coordinate arrays

    Returns
    -------
    scale : dict[str, float]
        Scale factors for each dimension
    translation : dict[str, float]
        Translation offsets for each dimension

    Notes
    -----
    Implements the inverse of transforms_to_coords for round-tripping.

    For uniformly spaced coordinates, extracts:
    - scale: spacing between coordinate values
    - translation: first coordinate value

    If OME metadata is stored in attrs, uses that directly.

    References
    ----------
    https://github.com/JaneliaSciComp/xarray-ome-ngff/blob/main/src/xarray_ome_ngff/v04/multiscale.py#L219-L224
    """
    # Try to use stored OME metadata if available
    if "ome_scale" in dataset.attrs and "ome_translation" in dataset.attrs:
        return dataset.attrs["ome_scale"], dataset.attrs["ome_translation"]

    # Otherwise, compute from coordinates
    scale: dict[Hashable, float] = {}
    translation: dict[Hashable, float] = {}

    # Get the first data variable to access dimensions
    first_var = next(iter(dataset.data_vars))
    data_array = dataset[first_var]

    for dim in data_array.dims:
        if dim in dataset.coords:
            coord = dataset.coords[dim].values
            if len(coord) > 1:
                # Calculate scale as spacing between coordinates
                # Assumes uniform spacing
                scale[dim] = float(coord[1] - coord[0])
            else:
                scale[dim] = 1.0

            # Translation is the first coordinate value
            translation[dim] = float(coord[0])
        else:
            # No coordinate array, use defaults
            scale[dim] = 1.0
            translation[dim] = 0.0

    return scale, translation
