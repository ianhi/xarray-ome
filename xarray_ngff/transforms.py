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

    References
    ----------
    https://github.com/JaneliaSciComp/xarray-ome-ngff/blob/main/src/xarray_ome_ngff/v04/multiscale.py#L219-L224
    """
    scale: dict[Hashable, float] = {}
    translation: dict[Hashable, float] = {}

    # Derive the axis set from every data variable's dims (their union), so a
    # multi-variable / disjoint-dim Dataset does not silently drop an axis's
    # transform. For a single-var Dataset this is just that var's dims.
    for dim in dataset.dims:
        if dim in dataset.coords:
            coord = dataset.coords[dim].values
            # Only numeric (physical/spatial-temporal) coordinates yield a
            # scale/translation. Non-numeric coords -- notably the object/string
            # channel-label `c` coord the reader adds from omero -- are skipped:
            # subtracting/casting them to float would raise, and they carry no
            # affine transform. ngff-zarr then applies its identity default.
            if not np.issubdtype(coord.dtype, np.number):
                continue
            # Degenerate size-0 axis: no sample to read, skip (no transform).
            if len(coord) == 0:
                continue
            if len(coord) > 1:
                # Calculate scale as spacing between coordinates
                # Assumes uniform spacing
                dim_scale = float(coord[1] - coord[0])
            else:
                # Size-1 axis: no spacing to measure, scale defaults to 1.0.
                dim_scale = 1.0

            # Translation is the first coordinate value
            dim_translation = float(coord[0])

            # Defensive: never write NaN/inf into a transform.
            if not (np.isfinite(dim_scale) and np.isfinite(dim_translation)):
                continue

            scale[dim] = dim_scale
            translation[dim] = dim_translation
        else:
            # No coordinate array, use defaults
            scale[dim] = 1.0
            translation[dim] = 0.0

    return scale, translation
