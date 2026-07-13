"""xarray indexes & coordinate transforms for OME-Zarr / NGFF.

The single home for every transform + index building block, organised by the
kind of NGFF coordinate transform they serve. Import everything from here::

    from xarray_ngff.indexes import TransformIndex, LensCoordinateTransform

The three cases, keyed on whether the transform is *separable* and *invertible*:

* **separable + invertible** (diagonal ``scale``/``translation``) ->
  :class:`TransformIndex` (1-D per axis, exact inverse); build the coordinates
  with :func:`transform_coords`.
* **non-separable + invertible** (general/shear ``affine``) ->
  :class:`CoordinateTransformIndex` with a matrix ``reverse`` (exact, no tree).
* **non-separable + non-invertible** (``displacements`` / lens) ->
  :class:`~xarray.indexes.NDPointIndex` (KD-tree over forward-mapped points).
"""

from __future__ import annotations

from ._affine import (
    AffineCoordinateTransform,
    AffineTransform,
    TransformIndex,
    transform_coords,
)
from ._lens import (
    DisplacementFieldTransform,
    LensCoordinateTransform,
    lens_dataarray,
    lens_world_coords,
)
from ._registration import (
    SequenceTransform,
    SequenceTransformIndex,
)
from ._stitched import (
    Tile,
    mosaic_bounds,
    place_tiles,
)

__all__ = [
    # diagonal / separable  -> 1-D affine index
    "AffineCoordinateTransform",
    # unified lazy coordinate index + builder (scalar / slice / N-D world bbox)
    "TransformIndex",
    "transform_coords",
    # non-separable + invertible affine  -> CoordinateTransformIndex w/ matrix reverse
    "AffineTransform",
    "SequenceTransform",
    "SequenceTransformIndex",
    # non-separable + non-invertible (lens / displacements)  -> NDPointIndex
    "LensCoordinateTransform",
    "DisplacementFieldTransform",
    "lens_world_coords",
    "lens_dataarray",
    # mosaic: many arrays aligned onto one shared regular grid (no custom index)
    "Tile",
    "place_tiles",
    "mosaic_bounds",
]
