"""Non-separable coordinate transforms for lens-distorted / warped images.

NGFF per-level transforms (scale + translation) are *diagonal*: separable per
axis, so each axis gets its own 1-D affine coordinate and selection is a cheap
1-D inverse (see :mod:`._affine`).

A **lens** transform (RFC-5 ``lens_correction``) is a different beast: a
*non-separable, nonlinear* 2-D map. A straight pixel row bends into a curved
line in physical space, so the physical location of a pixel can no longer be
written as one 1-D coordinate per axis --- it needs full 2-D coordinate arrays
``x(y, x)`` and ``y(y, x)``. And a lens map generally has **no closed-form
inverse**, so the affine trick of ``reverse``-ing a label back to a pixel does
not apply.

Two xarray building blocks combine to handle exactly this case:

* :class:`xarray.indexes.CoordinateTransform` --- its ``forward`` method
  *lazily generates* the curved 2-D world coordinates from the integer pixel
  grid. Nothing dense is stored; values are computed on demand. This is the
  https://xarray-indexes.readthedocs.io/blocks/transform.html pattern.

* :class:`xarray.indexes.NDPointIndex` --- builds a KD-tree over those 2-D
  world points so ``.sel(x=..., y=..., method="nearest")`` resolves a physical
  location to the nearest pixel *without needing an analytic inverse*. This is
  the https://xarray-indexes.readthedocs.io/blocks/ndpoint.html pattern.

:class:`LensCoordinateTransform` is a closed-form radial (Brown--Conrady)
model; :class:`DisplacementFieldTransform` reads a sampled displacement field
(the RFC-5 way). Only ``forward`` differs between them; everything downstream is
identical.
"""

from __future__ import annotations

from collections.abc import Hashable
from typing import Any

import numpy as np
import xarray as xr
from xarray.indexes import CoordinateTransform, CoordinateTransformIndex, NDPointIndex


class LensCoordinateTransform(CoordinateTransform):
    """Radial (barrel/pincushion) lens distortion mapping pixels -> world.

    The map is applied on a normalized frame centered at the optical center
    ``(cx, cy)`` and scaled by ``f`` (a pixel radius). With normalized radius
    ``r`` the radial distortion factor is::

        d(r) = 1 + k1 * r**2 + k2 * r**4

    ``k1 > 0`` gives pincushion, ``k1 < 0`` gives barrel distortion. ``forward``
    returns *2-D* world coordinate arrays, so the resulting ``x``/``y``
    coordinates each depend on both ``x`` and ``y`` dims --- the hallmark of a
    non-separable transform.
    """

    __slots__ = ("cx", "cy", "f", "k1", "k2")

    def __init__(
        self,
        *,
        width: int,
        height: int,
        k1: float,
        k2: float = 0.0,
        center: tuple[float, float] | None = None,
        f: float | None = None,
        dtype: Any = np.dtype(float),
    ):
        super().__init__(
            coord_names=["x", "y"],
            dim_size={"y": height, "x": width},
            dtype=dtype,
        )
        self.cx = float(center[0]) if center is not None else (width - 1) / 2
        self.cy = float(center[1]) if center is not None else (height - 1) / 2
        self.f = float(f) if f is not None else float(np.hypot(width, height) / 2)
        self.k1 = float(k1)
        self.k2 = float(k2)

    def forward(self, dim_positions: dict[str, Any]) -> dict[Hashable, Any]:
        ix = np.asarray(dim_positions["x"], dtype=float)
        iy = np.asarray(dim_positions["y"], dtype=float)
        xn = (ix - self.cx) / self.f
        yn = (iy - self.cy) / self.f
        r2 = xn**2 + yn**2
        d = 1.0 + self.k1 * r2 + self.k2 * r2**2
        return {
            "x": self.cx + self.f * d * xn,
            "y": self.cy + self.f * d * yn,
        }

    def reverse(self, coord_labels: dict[Hashable, Any]) -> dict[str, Any]:
        # A radial distortion has no closed-form inverse. Selection is routed
        # through NDPointIndex (a KD-tree over forward-mapped points) instead.
        raise NotImplementedError(
            "LensCoordinateTransform is forward-only; select via NDPointIndex (see lens_dataarray)."
        )

    def equals(self, other: CoordinateTransform, **kwargs: Any) -> bool:
        if not isinstance(other, LensCoordinateTransform):
            return False
        return bool(
            self.dim_size == other.dim_size
            and np.isclose(self.cx, other.cx)
            and np.isclose(self.cy, other.cy)
            and np.isclose(self.f, other.f)
            and np.isclose(self.k1, other.k1)
            and np.isclose(self.k2, other.k2)
        )


class DisplacementFieldTransform(CoordinateTransform):
    """Non-separable transform ``world = pixel + displacement(pixel)``.

    ``dy``/``dx`` are full-resolution displacement arrays (already upsampled
    from a sparsely-sampled field). ``forward`` looks them up with bilinear
    interpolation, so it also works at the fractional positions the coordinate
    machinery may request. This is the RFC-5 ``displacements`` semantics.
    """

    __slots__ = ("dy", "dx")

    def __init__(self, dy: np.ndarray, dx: np.ndarray, dtype: Any = np.dtype(float)):
        height, width = dy.shape
        super().__init__(coord_names=["x", "y"], dim_size={"y": height, "x": width}, dtype=dtype)
        self.dy = dy
        self.dx = dx

    def forward(self, dim_positions: dict[str, Any]) -> dict[Hashable, Any]:
        from scipy.ndimage import map_coordinates

        iy = np.asarray(dim_positions["y"], dtype=float)
        ix = np.asarray(dim_positions["x"], dtype=float)
        coords = np.stack([iy.ravel(), ix.ravel()])
        dy = map_coordinates(self.dy, coords, order=1, mode="nearest").reshape(iy.shape)
        dx = map_coordinates(self.dx, coords, order=1, mode="nearest").reshape(ix.shape)
        return {"x": ix + dx, "y": iy + dy}

    def reverse(self, coord_labels: dict[Hashable, Any]) -> dict[str, Any]:
        raise NotImplementedError(
            "DisplacementFieldTransform is forward-only; select via NDPointIndex."
        )


def lens_world_coords(transform: CoordinateTransform) -> xr.Coordinates:
    """Lazy 2-D ``x``/``y`` world coordinates from a non-separable transform.

    Uses :class:`CoordinateTransformIndex` so the coordinate *values* stay lazy
    (computed from ``forward`` on demand) rather than being densely stored.
    """
    return xr.Coordinates.from_xindex(CoordinateTransformIndex(transform))


def lens_dataarray(
    data: np.ndarray,
    *,
    k1: float,
    k2: float = 0.0,
    center: tuple[float, float] | None = None,
    f: float | None = None,
) -> xr.DataArray:
    """Wrap a 2-D image in curved lens ``x``/``y`` coords + an ``NDPointIndex``.

    The returned DataArray supports physical-space selection::

        da.sel(x=120.0, y=64.0, method="nearest")

    which returns the pixel whose *distorted* world location is nearest the
    requested physical point --- no analytic inverse required.
    """
    height, width = data.shape
    transform = LensCoordinateTransform(
        width=width, height=height, k1=k1, k2=k2, center=center, f=f
    )
    coords = lens_world_coords(transform)
    da = xr.DataArray(data, coords=coords, dims=("y", "x"))
    # Swap the forward-only transform index for a KD-tree over the same points
    # so .sel works in physical space. NDPointIndex materializes the 2-D coords
    # (a KD-tree needs concrete points); the transform gave us those lazily.
    return da.drop_indexes(["x", "y"]).set_xindex(["x", "y"], NDPointIndex)
