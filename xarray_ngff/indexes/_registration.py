"""Composed transforms with a stored inverse: RFC-5 ``bijection`` / ``sequence``.

The diagonal (``scale``/``translation``), general ``affine`` and ``displacements``
cases each handle a *single* transform. Real registration pipelines instead
**compose** transforms: warp with a dense displacement field, then apply a global
affine. RFC-5 encodes this with two wrappers:

* ``sequence`` --- an ordered list of sub-transforms, applied left to right.
* ``bijection`` --- a pair of ``sequence``\\ s, one ``forward`` and one
  ``inverse``. Because a composition of a general affine with a *sampled*
  displacement field has **no closed-form inverse**, RFC-5 stores the inverse
  explicitly (its own affine + its own displacement field) rather than asking a
  reader to invert anything.

That stored inverse is the whole point of this module. The lens example
(:mod:`._lens`) had only a ``forward`` map, so physical-space ``.sel`` fell back
to a KD-tree (:class:`~xarray.indexes.NDPointIndex`) that searches
forward-mapped points for the nearest match --- an *approximate* answer. Here we
have the exact inverse on disk, so :class:`SequenceTransform` implements
``reverse`` by *applying the stored inverse sequence*, and
:class:`~xarray.indexes.CoordinateTransformIndex` gives **exact** selection with
no tree.

Every transform here works in one shared frame: it maps a dict keyed by
``coord_names`` (physical positions along each axis) to another such dict. Steps
therefore compose by plain function composition on that dict.

Building blocks:

* :class:`AffineTransform` --- a general (non-diagonal) N-D affine
  ``world = A @ pos + b`` with an exact matrix ``reverse``.
* :class:`SequenceTransform` --- composes an ordered list of sub-transforms;
  ``forward`` applies them in order, ``reverse`` applies each sub-transform's
  ``reverse`` in reverse order, or --- for the ``bijection`` case where a step is
  a non-invertible sampled field --- applies a separately-supplied stored
  ``inverse``.
"""

from __future__ import annotations

from collections.abc import Hashable, Sequence
from typing import Any, cast

import numpy as np
from xarray import DataArray, Variable
from xarray.core.indexing import IndexSelResult
from xarray.indexes import CoordinateTransform, CoordinateTransformIndex

# The building blocks composed here -- AffineTransform (._affine) and
# DisplacementFieldTransform (._lens) -- are supplied by the caller as ready
# steps, so this module does not import them; get them from xarray_ngff.indexes.


class SequenceTransform(CoordinateTransform):
    """Ordered composition of sub-transforms (RFC-5 ``sequence`` / ``bijection``).

    All sub-transforms share this transform's ``coord_names`` and map a
    position-dict to a position-dict in that same frame, so ``forward`` just
    threads the dict through each step in order.

    ``reverse`` unwinds them:

    * if ``inverse`` is given (the ``bijection`` case, where at least one step is
      a sampled displacement field with no closed form), ``reverse`` *applies the
      stored inverse sequence* --- exact, from data on disk;
    * otherwise it applies each sub-transform's own ``reverse`` in reverse order
      (valid only when every step is analytically invertible).
    """

    __slots__ = ("_steps", "_inverse")

    def __init__(
        self,
        steps: Sequence[CoordinateTransform],
        *,
        inverse: SequenceTransform | None = None,
    ):
        if not steps:
            raise ValueError("SequenceTransform needs at least one step")
        first = steps[0]
        super().__init__(
            coord_names=list(first.coord_names),
            dim_size=dict(first.dim_size),
            dtype=first.dtype,
        )
        self._steps = list(steps)
        self._inverse = inverse

    def forward(self, dim_positions: dict[str, Any]) -> dict[Hashable, Any]:
        state = dict(dim_positions)
        for step in self._steps:
            state = dict(step.forward(state))
        return cast("dict[Hashable, Any]", state)

    def reverse(self, coord_labels: dict[Hashable, Any]) -> dict[str, Any]:
        if self._inverse is not None:
            # Exact: the stored inverse sequence maps world labels back to pixels.
            pixels = self._inverse.forward({str(k): v for k, v in coord_labels.items()})
            return {str(k): v for k, v in pixels.items()}
        state = dict(coord_labels)
        for step in reversed(self._steps):
            state = dict(step.reverse(state))
        return {str(k): v for k, v in state.items()}

    def equals(self, other: CoordinateTransform, **kwargs: Any) -> bool:
        if not isinstance(other, SequenceTransform):
            return False
        if len(self._steps) != len(other._steps):
            return False
        return all(a.equals(b) for a, b in zip(self._steps, other._steps))


class SequenceTransformIndex(CoordinateTransformIndex):
    """``CoordinateTransformIndex`` with an ergonomic point-wise ``.sel``.

    The base class only accepts ``method="nearest"`` with labels already wrapped
    in xarray objects. Following the pattern xarray's ``RangeIndex`` and the
    affine index use, this wraps plain scalars/arrays and assumes ``nearest``, so
    ``da.sel(x=..., y=...)`` works. Because the underlying transform's ``reverse``
    is the *stored inverse* (not a KD-tree), the resolved pixel is **exact** up to
    the round-to-nearest-pixel step.
    """

    def sel(
        self, labels: dict[Any, Any], method: Any = None, tolerance: Any = None
    ) -> IndexSelResult:
        if method is None:
            method = "nearest"  # physical labels are continuous
        wrapped = {}
        unwrap = False
        for name, label in labels.items():
            if isinstance(label, (Variable, DataArray)):
                wrapped[name] = label
            else:
                arr = np.asarray(label)
                wrapped[name] = Variable("_points", np.atleast_1d(arr))
                unwrap = arr.ndim == 0
        result = super().sel(wrapped, method=method, tolerance=tolerance)
        if unwrap:
            result = IndexSelResult({d: v.values[0] for d, v in result.dim_indexers.items()})
        return result
