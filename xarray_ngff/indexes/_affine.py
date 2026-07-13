"""Lazy, transform-backed physical coordinates for OME-Zarr axes.

NGFF per-level coordinate transforms are *diagonal*: a pure ``scale`` followed
by a ``translation`` with no rotation or shear. A diagonal affine is separable
per axis, so the physical world coordinate along each axis is a 1-D affine of
the integer pixel position::

    phys(i) = scale * i + translation

Rather than materializing dense coordinate arrays (one float per pixel, per
axis, per pyramid level), each spatial coordinate is backed by an
:class:`xarray.indexes.CoordinateTransformIndex` wrapping a small
:class:`AffineCoordinateTransform`. Coordinate values are computed lazily from
``(scale, translation)`` on demand; nothing dense sits in memory until
``.values`` / ``.compute()`` forces it.

:class:`TransformIndex` subclasses the generic index to give an ergonomic
``.sel`` (plain scalars, label slices, N-D world bounding boxes), and
:func:`transform_coords` builds one lazy world coordinate per axis, each backed
by a :class:`TransformIndex`.
"""

from __future__ import annotations

from collections.abc import Hashable, Mapping, Sequence
from typing import Any, cast

import numpy as np
from xarray import Coordinates
from xarray.core.indexing import IndexSelResult
from xarray.indexes import CoordinateTransform, CoordinateTransformIndex


class AffineCoordinateTransform(CoordinateTransform):
    """1-D affine ``phys = scale * pixel + translation`` for one axis.

    Separable component of a diagonal NGFF coordinate transform. Values are
    never stored; they are recomputed from ``(scale, translation)`` in
    :meth:`forward`.
    """

    __slots__ = ("scale", "translation")

    def __init__(
        self,
        scale: float,
        translation: float,
        size: int,
        coord_name: Hashable,
        dim: str,
        dtype: Any = None,
    ):
        super().__init__([coord_name], {dim: size}, dtype=dtype)
        self.scale = float(scale)
        self.translation = float(translation)

    @property
    def coord_name(self) -> Hashable:
        return self.coord_names[0]

    @property
    def dim(self) -> str:
        return self.dims[0]

    def forward(self, dim_positions: dict[str, Any]) -> dict[Hashable, Any]:
        positions = dim_positions[self.dim]
        return {self.coord_name: self.scale * positions + self.translation}

    def reverse(self, coord_labels: dict[Hashable, Any]) -> dict[str, Any]:
        labels = coord_labels[self.coord_name]
        return {self.dim: (labels - self.translation) / self.scale}

    def equals(self, other: CoordinateTransform, **kwargs: Any) -> bool:
        if not isinstance(other, AffineCoordinateTransform):
            return False
        return bool(
            np.isclose(self.scale, other.scale)
            and np.isclose(self.translation, other.translation)
            and self.dim_size == other.dim_size
        )


class TransformIndex(CoordinateTransformIndex):
    """``CoordinateTransformIndex`` with world-unit ``.sel`` for any invertible transform.

    The base :class:`~xarray.indexes.CoordinateTransformIndex` only accepts
    point-wise ``method="nearest"`` selection with labels already wrapped in
    xarray objects. This subclass overrides :meth:`sel` so that plain scalars,
    label slices, and N-D world bounding boxes all work, resolving positions
    through the transform's :meth:`~xarray.indexes.CoordinateTransform.reverse`.

    Three selection modes are recognised:

    * **scalar** --- when no label is a ``slice`` and every label is a plain
      scalar, each is mapped to a pixel via ``reverse``, rounded, and clipped
      to ``[0, size - 1]``. Works for 1-D and N-D transforms.
    * **bounding box** --- when *any* label is a ``slice``, the provided slices
      are treated as a world-space bounding box. The bbox boundary is sampled
      (a grid of points), reversed to pixel space, and each dimension is
      selected with an inclusive integer slice covering the sampled extent.
      For the 1-D single-coord case this reduces to an inclusive, sign-agnostic
      label slice (``ceil``/``floor`` endpoints).
    * **point-wise** --- anything else (``DataArray`` / ``Variable`` labels) is
      delegated to :meth:`CoordinateTransformIndex.sel`.

    Notes
    -----
    The covering bounding box is a *superset* for warped (non-affine)
    transforms: the returned rectangular pixel tile is guaranteed to contain
    the requested world bbox but may extend slightly beyond it.

    This requires an *invertible* transform --- ``reverse`` must map world
    coordinates back to pixel positions. Non-finite ``reverse`` outputs (e.g.
    from points outside the invertible domain) are dropped before computing
    the pixel extent.
    """

    # number of samples per spanned coordinate when tracing a bbox boundary
    _BBOX_SAMPLES = 64

    @property
    def _transform(self) -> CoordinateTransform:
        return cast(CoordinateTransform, self.transform)

    def sel(
        self, labels: dict[Any, Any], method: Any = None, tolerance: Any = None
    ) -> IndexSelResult:
        tr = self._transform

        any_slice = any(isinstance(v, slice) for v in labels.values())
        all_scalar = not any_slice and all(np.isscalar(v) for v in labels.values())

        # ---- scalar labels -> nearest integer pixel (clipped) ---------------
        if all_scalar:
            world = {name: np.asarray(float(v)) for name, v in labels.items()}
            pixel = tr.reverse(world)
            out: dict[str, Any] = {}
            for dim in tr.dims:
                p = float(np.asarray(pixel[dim]))
                size = int(tr.dim_size[dim])
                out[dim] = int(np.clip(np.round(p), 0, size - 1))
            return IndexSelResult(out)

        # ---- slice label(s) -> covering world bounding box ------------------
        if any_slice:
            # full world extent of every coord, used for any coord left free
            pixel_corners = {d: np.array([0.0, tr.dim_size[d] - 1.0], dtype=float) for d in tr.dims}
            full = tr.forward(pixel_corners)

            samples: dict[Hashable, np.ndarray] = {}
            for name in tr.coord_names:
                lab = labels.get(name)
                if isinstance(lab, slice):
                    # Open ends behave like an unconstrained end for that side:
                    # fall back to the full world extent of this coord.
                    ext = np.asarray(full[name], dtype=float).ravel()
                    lo = float(ext.min()) if lab.start is None else float(cast(float, lab.start))
                    hi = float(ext.max()) if lab.stop is None else float(cast(float, lab.stop))
                    samples[name] = np.linspace(lo, hi, self._BBOX_SAMPLES)
                else:
                    ext = np.asarray(full[name], dtype=float).ravel()
                    samples[name] = np.linspace(
                        float(ext.min()), float(ext.max()), self._BBOX_SAMPLES
                    )

            # outer product of the per-coord samples -> dense boundary grid
            names = list(tr.coord_names)
            grids = np.meshgrid(*(samples[n] for n in names), indexing="ij")
            world = {n: g.ravel() for n, g in zip(names, grids)}

            pixel = tr.reverse(world)
            out = {}
            for dim in tr.dims:
                size = int(tr.dim_size[dim])
                p = np.asarray(pixel[dim], dtype=float).ravel()
                p = p[np.isfinite(p)]
                if p.size == 0:
                    out[dim] = slice(0, 0)
                    continue
                lo = max(int(np.floor(p.min())), 0)
                hi = min(int(np.ceil(p.max())), size - 1)
                out[dim] = slice(lo, hi + 1) if hi >= lo else slice(0, 0)
            return IndexSelResult(out)

        # ---- point-wise DataArray / Variable labels -> delegate -------------
        return super().sel(labels, method=method, tolerance=tolerance)


def transform_coords(
    sizes: Mapping[str, int],
    scale: Mapping[str, float] | None = None,
    translate: Mapping[str, float] | None = None,
    *,
    names: Sequence[Hashable] | None = None,
    dims: Sequence[str] | None = None,
) -> Coordinates:
    """Build lazy affine world coordinates, one per axis, each with a :class:`TransformIndex`.

    Each axis becomes a 1-D :class:`AffineCoordinateTransform`
    (``world = scale * pixel + translate``) wrapped in a :class:`TransformIndex`
    and merged into a single :class:`xarray.Coordinates`. Coordinate values are
    computed lazily and ``.sel`` accepts world-unit labels (or pixel labels
    under the identity fallback).

    Parameters
    ----------
    sizes : mapping of str to int
        ``{dim: size}`` for each axis. Iteration order defines the axis order.
    scale : mapping of str to float, optional
        ``{axis: scale}``. Missing axes default to ``1.0`` (identity).
    translate : mapping of str to float, optional
        ``{axis: translation}``. Missing axes default to ``0.0`` (identity).
    names : sequence of hashable, optional
        Coordinate names, one per axis. Defaults to the ``sizes`` keys, so the
        coordinate name matches the dimension name.
    dims : sequence of str, optional
        Dimension names, one per axis. Defaults to the ``sizes`` keys.

    Returns
    -------
    xarray.Coordinates
        Lazy world coordinates whose ``.sel`` works in world units. With no
        ``scale``/``translate`` (the identity fallback) the coordinates are the
        integer pixel positions.

    Notes
    -----
    The identity fallback (no ``scale``/``translate``) is the "no transform"
    case: it must yield working pixel coordinates.
    """
    scale = {} if scale is None else dict(scale)
    translate = {} if translate is None else dict(translate)

    keys = list(sizes.keys())
    names = list(keys) if names is None else list(names)
    dims = list(keys) if dims is None else list(dims)
    if not (len(keys) == len(names) == len(dims)):
        raise ValueError("sizes, names, and dims must all have the same length")

    coords: Coordinates | None = None
    for key, name, dim in zip(keys, names, dims):
        transform = AffineCoordinateTransform(
            scale=float(scale.get(key, 1.0)),
            translation=float(translate.get(key, 0.0)),
            size=int(sizes[key]),
            coord_name=name,
            dim=dim,
        )
        axis_coords = Coordinates.from_xindex(TransformIndex(transform))
        coords = axis_coords if coords is None else coords.merge(axis_coords).coords

    if coords is None:
        return Coordinates()
    return coords


class AffineTransform(CoordinateTransform):
    """General N-D affine ``world = A @ pixel + t`` with an exact matrix inverse.

    The *non-separable but invertible* case, between the diagonal
    :class:`AffineCoordinateTransform` (one axis at a time) and the
    non-invertible lens / displacement map. Because ``A`` may be non-diagonal
    (rotation, shear, off-diagonal coupling), each world coordinate is a linear
    combination of *all* pixel positions, so the coordinates are non-separable
    and cannot be written as one 1-D coord per axis. But an affine is exactly
    invertible, so :meth:`reverse` applies ``A**-1 @ (world - t)`` and physical
    selection stays **exact** --- no KD-tree, unlike the lens case.

    Two RFC-5-friendly matrix layouts are accepted:

    * a plain ``(n, n)`` linear part ``A`` plus an optional ``translation`` ``t``;
    * a homogeneous ``(n, n+1)`` block ``[A | t]`` (RFC-5's ``affine`` layout),
      in which case ``translation`` must be ``None``.

    ``dims`` (pixel dimension names, one per column of ``A``) default to
    ``coord_names`` (world names, one per row); pass ``dims`` explicitly when
    they differ, e.g. deskewing pixel ``(z, y)`` into physical ``(z_um, y_um)``.
    """

    __slots__ = ("matrix", "inverse", "translation")

    def __init__(
        self,
        matrix: np.ndarray | Sequence[Sequence[float]],
        coord_names: Sequence[Hashable],
        *,
        dim_sizes: dict[str, int],
        dims: Sequence[str] | None = None,
        translation: np.ndarray | Sequence[float] | None = None,
        dtype: Any = np.dtype(float),
    ):
        matrix = np.asarray(matrix, dtype=float)
        n = matrix.shape[0]
        if matrix.shape == (n, n + 1):  # homogeneous [A | t]
            if translation is not None:
                raise ValueError("pass translation in the matrix or separately, not both")
            linear, offset = matrix[:, :n], matrix[:, n]
        elif matrix.shape == (n, n):
            linear = matrix
            offset = np.zeros(n) if translation is None else np.asarray(translation, float)
        else:
            raise ValueError(f"matrix must be (n, n) or (n, n+1); got {matrix.shape}")

        dim_names = list(coord_names) if dims is None else list(dims)
        if len(coord_names) != n or len(dim_names) != n:
            raise ValueError("coord_names and dims must match the matrix rank")

        super().__init__(
            coord_names=list(coord_names),
            dim_size={str(d): int(dim_sizes[str(d)]) for d in dim_names},
            dtype=dtype,
        )
        self.matrix = linear
        # np.linalg.inv raises LinAlgError on a singular matrix -> exactly the
        # "not invertible" case that would force a KD-tree fallback instead.
        self.inverse = np.linalg.inv(linear)
        self.translation = offset
        # ``self.coord_names`` and ``self.dims`` are set by the base class (in the
        # order given), so there is no need to keep private copies.

    def _stack(self, positions: dict[Any, Any], keys: Sequence[Hashable]) -> np.ndarray:
        arrays = [np.asarray(positions[k], dtype=float) for k in keys]
        shape = np.broadcast_shapes(*(a.shape for a in arrays)) if arrays else ()
        return np.stack([np.broadcast_to(a, shape) for a in arrays])

    def forward(self, dim_positions: dict[str, Any]) -> dict[Hashable, Any]:
        pixel = self._stack(dim_positions, self.dims)
        world = self.matrix @ pixel.reshape(pixel.shape[0], -1) + self.translation[:, None]
        world = world.reshape(pixel.shape)
        return {name: world[i] for i, name in enumerate(self.coord_names)}

    def reverse(self, coord_labels: dict[Hashable, Any]) -> dict[str, Any]:
        """Exact inverse ``pixel = A**-1 @ (world - t)`` --- no KD-tree needed."""
        world = self._stack(coord_labels, self.coord_names)
        pixel = self.inverse @ (world.reshape(world.shape[0], -1) - self.translation[:, None])
        pixel = pixel.reshape(world.shape)
        return {dim: pixel[i] for i, dim in enumerate(self.dims)}

    def equals(self, other: CoordinateTransform, **kwargs: Any) -> bool:
        if not isinstance(other, AffineTransform):
            return False
        return bool(
            self.dim_size == other.dim_size
            and self.coord_names == other.coord_names
            and self.dims == other.dims
            and np.allclose(self.matrix, other.matrix)
            and np.allclose(self.translation, other.translation)
        )
