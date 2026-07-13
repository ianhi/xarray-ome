"""Reading OME-Zarr files into xarray DataTree and Dataset objects.

Re-bases the reader onto the validated *synthesis* design (see
``research/`` / ``experiments/``): lazy, transform-backed physical coordinates
plus a verbatim ``ome`` carrier for lossless, forward-compatible round-trips.

Each resolution level becomes a Dataset with:

- one image variable named from the NGFF image name,
- lazy physical coordinates on the spatial/time axes, backed by
  :class:`~xarray_ngff.indexes.TransformIndex` (ergonomic ``.sel``),
- CF-style ``units`` + ``axis_type`` coordinate attrs read from the NGFF axes,
- omero channel labels mapped onto the ``c`` coordinate when present
  (graceful integer-``c`` fallback when absent).

The verbatim raw ``ome`` block is carried on the root node's ``attrs["ome"]``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import numpy as np
import xarray as xr
from ngff_zarr import from_ngff_zarr  # type: ignore[import-untyped]

from ._store_utils import detect_store_type, read_ome_block
from .indexes import transform_coords

if TYPE_CHECKING:
    from pathlib import Path

    from ngff_zarr import NgffImage  # type: ignore[import-untyped]

# Axes that get a lazy affine physical coordinate. Channel ("c") is unitless and
# carries categorical labels (or falls back to integer positions), not a sampled
# physical axis, so it never gets an affine index.
_PHYSICAL_AXES = ("t", "z", "y", "x")


def _channel_labels_from_ome(ome: dict[str, Any] | None) -> list[str] | None:
    """Channel labels from an ``ome`` block's omero block, or None if absent.

    Returns ``None`` (not an error) when the store has no omero block so callers
    can fall back gracefully to a positional/integer ``c`` axis.
    """
    if not ome:
        return None
    omero = ome.get("omero")
    if not isinstance(omero, dict):
        return None
    channels = omero.get("channels")
    if not channels:
        return None
    return [ch.get("label", str(i)) for i, ch in enumerate(channels)]


def _axis_types_from_ome(ome: dict[str, Any] | None) -> dict[str, str | None]:
    """Map axis name -> NGFF axis ``type`` (e.g. "space", "time", "channel")."""
    if not ome:
        return {}
    multiscales = ome.get("multiscales")
    if not multiscales:
        return {}
    axes = multiscales[0].get("axes", [])
    return {a["name"]: a.get("type") for a in axes}


def _build_level_dataset(
    image: NgffImage,
    channel_labels: list[str] | None,
    axis_type: dict[str, str | None],
) -> xr.Dataset:
    """Build a single-level Dataset with lazy coords + CF attrs from an NgffImage."""
    dims = tuple(image.dims)
    var_name = image.name or "image"
    ds = xr.Dataset({var_name: (dims, image.data)})

    # omero channel labels on the `c` coordinate (graceful fallback to integers).
    if channel_labels is not None and "c" in dims and len(channel_labels) == ds.sizes["c"]:
        ds = ds.assign_coords(c=("c", np.asarray(channel_labels, dtype=object)))
        ds["c"].attrs["axis_type"] = axis_type.get("c", "channel") or "channel"

    # Lazy, transform-backed physical coordinates on the present spatial/time axes.
    # Build one call to ``transform_coords`` for the physical axes actually in
    # ``dims``. A *missing* scale/translation falls back to identity (1.0/0.0)
    # via ``.get(..., default)`` -- the "no world transform" case must not raise;
    # it simply yields honest integer-pixel coordinates.
    physical = [axis for axis in _PHYSICAL_AXES if axis in dims]
    if physical:
        sizes = {axis: ds.sizes[axis] for axis in physical}
        scale = {axis: image.scale.get(axis, 1.0) for axis in physical}
        translate = {axis: image.translation.get(axis, 0.0) for axis in physical}
        ds = ds.assign_coords(transform_coords(sizes, scale, translate))

        axes_units = image.axes_units
        for axis in physical:
            unit = axes_units.get(axis) if axes_units is not None else None
            # NEVER fabricate a unit: absent NGFF unit -> no ``units`` attr (an
            # honest pixel coordinate under the identity fallback).
            if unit is not None:
                ds[axis].attrs["units"] = unit
            if axis_type.get(axis) is not None:
                ds[axis].attrs["axis_type"] = axis_type[axis]

    return ds


def open_ngff_datatree(path: str | Path, validate: bool = False) -> xr.DataTree:
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
        DataTree with one child node per resolution level, named ``"0"``,
        ``"1"``, ... Each node carries lazy physical coordinates. The verbatim
        ``ome`` metadata block is carried on the root node's ``attrs["ome"]`` for
        lossless, forward-compatible round-trips.

    Raises
    ------
    ValueError
        If the OME-Zarr store is not a simple multiscale image (e.g. HCS plate).
    """
    store = str(path)
    store_type = detect_store_type(store)

    if store_type == "unknown":
        msg = (
            f"The zarr store at '{store}' does not appear to be an OME-Zarr store. "
            "It may be a regular zarr file. Try opening with engine='zarr' instead."
        )
        raise ValueError(msg)

    if store_type == "hcs":
        msg = (
            f"The OME-Zarr store at '{store}' appears to be an HCS (High Content "
            "Screening) plate structure, which is not yet supported. "
            "Currently only simple multiscale images are supported."
        )
        raise ValueError(msg)

    multiscales = from_ngff_zarr(store, validate=validate)
    # Read the raw `ome` block ONCE: it feeds channel labels, per-axis types,
    # and the verbatim carrier.
    ome = read_ome_block(store)
    channel_labels = _channel_labels_from_ome(ome)
    axis_type = _axis_types_from_ome(ome)

    nodes: dict[str, xr.Dataset] = {}
    for level, image in enumerate(multiscales.images):
        nodes[f"/{level}"] = _build_level_dataset(image, channel_labels, axis_type)

    # Carrier: the verbatim `ome` block on the root -> nothing the parser dropped
    # is lost on round-trip.
    nodes["/"] = xr.Dataset(attrs={"ome": ome} if ome is not None else {})
    return xr.DataTree.from_dict(nodes)


def open_ngff_dataset(path: str | Path, resolution: int = 0, validate: bool = False) -> xr.Dataset:
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
        Dataset for the requested resolution level, built the same way as a
        DataTree node (lazy coords, CF attrs, channel labels). The verbatim
        ``ome`` block is carried on ``ds.attrs["ome"]``.

    Raises
    ------
    ValueError
        If the OME-Zarr store is not a simple multiscale image (e.g. HCS plate),
        or if the requested resolution level does not exist.
    """
    store = str(path)
    store_type = detect_store_type(store)

    if store_type == "unknown":
        msg = (
            f"The zarr store at '{store}' does not appear to be an OME-Zarr store. "
            "It may be a regular zarr file. Try opening with engine='zarr' instead."
        )
        raise ValueError(msg)

    if store_type == "hcs":
        msg = (
            f"The OME-Zarr store at '{store}' appears to be an HCS (High Content "
            "Screening) plate structure, which is not yet supported. "
            "Currently only simple multiscale images are supported."
        )
        raise ValueError(msg)

    multiscales = from_ngff_zarr(store, validate=validate)

    if resolution >= len(multiscales.images):
        msg = (
            f"Resolution level {resolution} not found. "
            f"Available levels: 0-{len(multiscales.images) - 1}"
        )
        raise ValueError(msg)

    ome = read_ome_block(store)
    channel_labels = _channel_labels_from_ome(ome)
    axis_type = _axis_types_from_ome(ome)

    image = multiscales.images[resolution]
    ds = _build_level_dataset(image, channel_labels, axis_type)
    if ome is not None:
        ds.attrs["ome"] = ome
    return ds
