"""Tests for :class:`TransformIndex` and :func:`transform_coords`."""

from __future__ import annotations

from typing import Any

import numpy as np
import xarray as xr
from xarray import Coordinates
from xarray.indexes import CoordinateTransform

from xarray_ngff.indexes import (
    TransformIndex,
    transform_coords,
)


def _dataset(size: int, scale: float, translate: float = 0.0, name: str = "x") -> xr.Dataset:
    """A 1-D dataset whose ``name`` coord is a lazy affine :class:`TransformIndex`."""
    coords = transform_coords({name: size}, {name: scale}, {name: translate})
    return xr.DataArray(
        np.arange(size, dtype=float), dims=name, coords=coords, name="img"
    ).to_dataset()


# --------------------------------------------------------------------------- #
# identity                                                                     #
# --------------------------------------------------------------------------- #
def test_identity_coords_and_lazy_backing() -> None:
    ds = _dataset(8, scale=1.0)
    # coords == arange
    np.testing.assert_array_equal(ds["x"].values, np.arange(8))
    # scalar sel picks the element at pixel 5
    assert float(ds.img.sel(x=5)) == 5.0
    # coordinate is lazy (transform-backed)
    assert type(ds["x"].variable._data).__name__ == "CoordinateTransformIndexingAdapter"


# --------------------------------------------------------------------------- #
# affine 1-D                                                                   #
# --------------------------------------------------------------------------- #
def test_affine_scalar_sel() -> None:
    ds = _dataset(8, scale=6.0)  # world = 6 * pixel
    # world 30 -> pixel 5
    assert float(ds.img.sel(x=30.0)) == 5.0


def test_affine_inclusive_slice() -> None:
    ds = _dataset(8, scale=6.0)  # world = [0, 6, 12, 18, 24, 30, 36, 42]
    sub = ds.sel(x=slice(12.0, 30.0))
    np.testing.assert_array_equal(sub["x"].values, [12.0, 18.0, 24.0, 30.0])


def test_affine_open_ended_slices() -> None:
    # world = [0, 6, 12, 18, 24, 30, 36, 42]
    ds = _dataset(8, scale=6.0)

    # closed reference: [12, 30] -> [12, 18, 24, 30]
    closed = ds.sel(x=slice(12.0, 30.0))["x"].values

    # open start behaves like unconstrained low end: everything up to 12
    open_lo = ds.sel(x=slice(None, 12.0))["x"].values
    np.testing.assert_array_equal(open_lo, [0.0, 6.0, 12.0])

    # open stop behaves like unconstrained high end: everything from 24 on
    open_hi = ds.sel(x=slice(24.0, None))["x"].values
    np.testing.assert_array_equal(open_hi, [24.0, 30.0, 36.0, 42.0])

    # both ends open -> the full coordinate
    open_both = ds.sel(x=slice(None, None))["x"].values
    np.testing.assert_array_equal(open_both, ds["x"].values)

    # sanity: closed slice endpoints agree with the overlapping open slices
    np.testing.assert_array_equal(closed, [12.0, 18.0, 24.0, 30.0])


def test_affine_negative_scale_slice_sign_agnostic() -> None:
    # descending axis: world = [0, -6, -12, ...]
    ds = _dataset(8, scale=-6.0)  # world = [0, -6, -12, -18, -24, -30, -36, -42]
    sub = ds.sel(x=slice(-30.0, -12.0))
    np.testing.assert_array_equal(sorted(sub["x"].values), [-30.0, -24.0, -18.0, -12.0])


# --------------------------------------------------------------------------- #
# DataTree cross-level                                                         #
# --------------------------------------------------------------------------- #
def test_datatree_cross_level_world_slice() -> None:
    l0 = _dataset(8, scale=1.0)  # world 0..7
    l1 = _dataset(4, scale=2.0)  # world 0,2,4,6
    tree = xr.DataTree.from_dict({"scale0": l0, "scale1": l1})
    sub = tree.sel(x=slice(0.0, 4.0))
    np.testing.assert_array_equal(sub["scale0"].x.values, [0.0, 1.0, 2.0, 3.0, 4.0])
    np.testing.assert_array_equal(sub["scale1"].x.values, [0.0, 2.0, 4.0])


# --------------------------------------------------------------------------- #
# N-D world bbox                                                               #
# --------------------------------------------------------------------------- #
class Fisheye(CoordinateTransform):
    """Radial fisheye pixel <-> world; invertible, non-affine."""

    def __init__(self, nx: int, ny: int, k: float) -> None:
        super().__init__(("x_world", "y_world"), {"y_pixel": ny, "x_pixel": nx})
        self.nx, self.ny, self.k = nx, ny, k

    def _norm(self, xp: Any, yp: Any) -> tuple[Any, Any]:
        return (
            (np.asarray(xp) - (self.nx - 1) / 2) / ((self.nx - 1) / 2),
            (np.asarray(yp) - (self.ny - 1) / 2) / ((self.ny - 1) / 2),
        )

    def _denorm_x(self, xn: Any) -> Any:
        return xn * ((self.nx - 1) / 2) + (self.nx - 1) / 2

    def _denorm_y(self, yn: Any) -> Any:
        return yn * ((self.ny - 1) / 2) + (self.ny - 1) / 2

    def forward(self, dim_positions: dict[Any, Any]) -> dict[Any, Any]:
        xn, yn = self._norm(dim_positions["x_pixel"], dim_positions["y_pixel"])
        f = 1 / (1 - self.k * np.hypot(xn, yn) ** 2)
        return {"x_world": xn * f, "y_world": yn * f}

    def reverse(self, coord_labels: dict[Any, Any]) -> dict[Any, Any]:
        xw, yw = np.asarray(coord_labels["x_world"]), np.asarray(coord_labels["y_world"])
        rw = np.hypot(xw, yw)
        with np.errstate(divide="ignore", invalid="ignore"):
            pr = (np.sqrt(1 + 4 * self.k * rw**2) - 1) / (2 * self.k * rw)
        ratio = np.where(rw > 0, pr / rw, 1.0)
        xn, yn = xw * ratio, yw * ratio
        return {"x_pixel": self._denorm_x(xn), "y_pixel": self._denorm_y(yn)}

    def equals(self, other: Any, **kwargs: Any) -> bool:
        return isinstance(other, Fisheye) and (self.nx, self.ny, self.k) == (
            other.nx,
            other.ny,
            other.k,
        )


def test_nd_world_bbox_covers_request() -> None:
    nx = ny = 256
    idx = TransformIndex(Fisheye(nx, ny, 0.35))
    photo = np.arange(ny * nx, dtype=float).reshape(ny, nx)
    da = xr.DataArray(
        photo,
        dims=("y_pixel", "x_pixel"),
        coords=Coordinates.from_xindex(idx),
        name="photo",
    )
    sub = da.sel(x_world=slice(0.2, 0.6), y_world=slice(0.2, 0.6))
    # rectangular tile
    assert sub.sizes["x_pixel"] > 0 and sub.sizes["y_pixel"] > 0
    # world range covers (is a superset of) the requested bbox
    assert float(sub.x_world.min()) <= 0.2
    assert float(sub.x_world.max()) >= 0.6
    assert float(sub.y_world.min()) <= 0.2
    assert float(sub.y_world.max()) >= 0.6


# --------------------------------------------------------------------------- #
# transform_coords identity default                                           #
# --------------------------------------------------------------------------- #
def test_transform_coords_identity_default() -> None:
    coords = transform_coords({"x": 10})
    da = xr.DataArray(np.arange(10.0), dims="x", coords=coords, name="v")
    # identity -> pixel coordinates
    np.testing.assert_array_equal(da["x"].values, np.arange(10))
    # working sel
    assert float(da.sel(x=7)) == 7.0
    assert type(da["x"].variable._data).__name__ == "CoordinateTransformIndexingAdapter"


def test_transform_coords_multi_axis() -> None:
    coords = transform_coords({"y": 4, "x": 3}, {"y": 2.0, "x": 10.0})
    da = xr.DataArray(np.zeros((4, 3)), dims=("y", "x"), coords=coords, name="v")
    np.testing.assert_array_equal(da["y"].values, [0.0, 2.0, 4.0, 6.0])
    np.testing.assert_array_equal(da["x"].values, [0.0, 10.0, 20.0])
