"""Placing many tile arrays into one shared world frame (image mosaics).

The affine and lens indexes (:mod:`._affine`, :mod:`._lens`) both answer the
question "for *one* array, where does each pixel land in physical space?".
Stitching is a structurally different question. Here there are **many arrays**
--- the tiles of a mosaic --- and a **single shared world coordinate system**.
Each tile is placed into that frame by its own NGFF ``translation`` transform
(``tile_i -> world``): a pure diagonal offset, no scale or rotation.

Because a translation is *separable* and (here) integer, every tile stays a
**regular grid** and they all live on one shared regular world lattice. That is
the key difference from the lens / registration cases: those warp each pixel to
an *irregular* physical location and need a custom index (a KD-tree, or a
transform with a ``reverse``) to make ``.sel`` work. A translated mosaic needs
**none of that** --- xarray's ordinary coordinate *alignment* drops each tile
onto the shared grid, and selection is then a plain index lookup. So this module
is deliberately thin: it just builds the tiles' world coordinates; the notebook
combines them with stock xarray and calls plain ``.sel``.

* :class:`Tile` --- a tile's pixel array plus its ``tile -> world`` offset.
* :func:`place_tiles` --- give each tile its 1-D world coordinate per axis
  (``phys = pixel + offset``), reusing the diagonal :class:`~._affine.TransformIndex`.
* :func:`mosaic_bounds` --- the world extent of the whole mosaic.

This is the "many arrays, one coordinate system" case; it pairs with the
multiscale / ``DataTree`` concerns rather than with single-array index design.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import xarray as xr

from ._affine import transform_coords


@dataclass(frozen=True)
class Tile:
    """One mosaic tile: its pixel data plus its ``tile -> world`` offset.

    ``data`` is an N-D pixel array; ``dims`` names its axes (e.g. ``("y", "x")``
    for 2-D or ``("z", "y", "x")`` for 3-D). ``translation`` maps each named
    world axis to the tile's offset along it (``phys = pixel + offset``); it is
    keyed by *axis name*, not position, so callers never have to line up the
    NGFF ``world`` axis order against the tile's own dim order.
    """

    name: str
    data: np.ndarray
    dims: tuple[str, ...]
    translation: dict[str, float]

    def __post_init__(self) -> None:
        if self.data.ndim != len(self.dims):
            raise ValueError(
                f"tile {self.name!r}: data has {self.data.ndim} dims but dims={self.dims}"
            )
        missing = set(self.dims) - set(self.translation)
        if missing:
            raise ValueError(f"tile {self.name!r}: no translation for axes {sorted(missing)}")


def place_tiles(tiles: list[Tile]) -> dict[str, xr.DataArray]:
    """Give each tile 1-D world coordinates + a lazy affine index per axis.

    A ``translation`` is a diagonal (separable) transform, so the world
    coordinate along each axis is just ``phys = pixel + offset`` --- one
    :class:`~._affine.TransformIndex` per axis, no dense arrays. Each returned
    DataArray is expressed in the shared ``world`` frame, so stock xarray
    (``align`` / label-based assignment) can merge them into one mosaic on which
    plain ``.sel`` works --- no custom mosaic index required.
    """
    placed: dict[str, xr.DataArray] = {}
    for tile in tiles:
        # translation is separable -> one lazy 1-D affine per axis
        # (phys = 1 * pixel + offset), reusing the diagonal machinery.
        sizes = {axis: int(size) for axis, size in zip(tile.dims, tile.data.shape)}
        coords = transform_coords(
            sizes,
            scale={axis: 1.0 for axis in tile.dims},
            translate={axis: float(tile.translation[axis]) for axis in tile.dims},
        )
        placed[tile.name] = xr.DataArray(tile.data, coords=coords, dims=tile.dims, name=tile.name)
    return placed


def mosaic_bounds(tiles: list[Tile]) -> dict[str, tuple[float, float]]:
    """World-frame ``(min, max)`` extent of the whole mosaic, per axis."""
    axes = tiles[0].dims
    bounds: dict[str, tuple[float, float]] = {}
    for axis in axes:
        lo = min(t.translation[axis] for t in tiles)
        hi = max(t.translation[axis] + t.data.shape[t.dims.index(axis)] for t in tiles)
        bounds[axis] = (float(lo), float(hi))
    return bounds
