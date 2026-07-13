# Things to upstream (not now — parked)

Ideas that belong in xarray itself, deferred so we don't block the package on an
upstream review cycle. Revisit after the xarray-ome package + RFC settle.

## 1. Scalar + slice `.sel` on `CoordinateTransformIndex`

**What:** `xarray.indexes.CoordinateTransformIndex.sel` currently only supports
point-wise (`DataArray`/`Variable`) labels with `method="nearest"`. It rejects a
plain scalar (`sel(x=3.0)`) and a label slice (`sel(x=slice(a, b))`).

**Why it should exist:** when the transform is invertible, both are trivially
resolvable via `transform.reverse()`:

- scalar `v` → `round(reverse(v))` → integer position;
- slice `(a, b)` → `reverse([a, b])` → inclusive integer slice (sign-agnostic,
  ceil/floor the endpoints).

We prototyped this as `SliceableTransformIndex` (a ~20-line subclass) in
`xarray_ome/indexes/_affine.py` and it works through `DataTree.sel` for
cross-level multiscale region selection. The logic generalizes to *any*
invertible monotonic 1-D transform (affine, log, time-base), which is why it is a
natural built-in feature rather than a per-library patch.

**Comparison evidence:** `experiments/lazy_vs_dense_coords.ipynb` shows the lazy
sliceable index and a dense `PandasIndex` producing identical `.sel` results.

**Plan when we do it:** open an xarray issue → PR adding slice/scalar handling to
`CoordinateTransformIndex.sel` (with the rounding behaviour made explicit /
customizable, per the existing TODO in that method). Once merged, delete our
`SliceableTransformIndex` subclass and use the built-in directly.

## 2. Bug (RESOLVED upstream): length-1 selection on a `CoordinateTransform`-backed dim raised

**Status:** **fixed in xarray 2026.1.0** — no longer an open item. Surfaced by the
property suite (`tests/test_property_rules.py`) when the project was on a stale
lock at xarray 2025.9.0. Broken on `<=2025.9.1`, fixed on `2026.1.0`. We bumped
the dependency floor to `xarray>=2026.1.0`; the pinned strict-`xfail` became a
plain passing regression test (`test_sel_size1_axis`) and the `size<2` skip in
`test_sel_always_works` was removed. Kept below for the record.

**What:** reducing a lazy `CoordinateTransform`-backed dimension to **length 1**
builds a 0-d coordinate and raises
`ValueError: dimensions ('y',) must have the same length as the number of data
dimensions, ndim=0`. It fires for every narrowing-to-one op — `isel(y=[0])`,
`isel(y=slice(0, 1))`, and therefore `sel(y=slice(v, v))` — and for any axis that
is *already* size 1 (single z-slice / single timepoint). Scalar `isel(y=0)`
(drops the dim) and any result of size ≥ 2 are fine.

**Scope:** it is **not** our code — it reproduces with a bare
`xarray.indexes.CoordinateTransformIndex` and a trivial `CoordinateTransform`
subclass (no `xarray_ngff` import). Returning `np.atleast_1d(...)` from
`forward` does **not** help; the 0-d array originates inside xarray's indexing
adapter, before `forward` is called. So there is no clean package-level
workaround short of materializing coords (which violates our lazy design, rule 1).

**Minimal repro:**

```python
import numpy as np, xarray as xr
from xarray.indexes import CoordinateTransform, CoordinateTransformIndex

class Lin(CoordinateTransform):
    def __init__(self, size): super().__init__(["y"], {"y": size})
    def forward(self, dp): return {"y": np.asarray(dp["y"], float) * 2.0}
    def reverse(self, cl): return {"y": np.asarray(cl["y"], float) / 2.0}
    def equals(self, other, **kw): return isinstance(other, Lin)

coords = xr.Coordinates.from_xindex(CoordinateTransformIndex(Lin(3)))
da = xr.DataArray(np.arange(3.0), dims="y", coords=coords)
da.isel(y=[0])   # -> ValueError (ndim=0); da.isel(y=[0, 1]) is fine
```

**Impact on us:** violates rule 2 (".sel always works") for size-1 physical
axes, which are common in microscopy. `test_sel_always_works` currently skips
size-1 axes; the strict `xfail` will flip to `xpass` when xarray fixes this —
that is the signal to drop the skip and the `xfail`.

**Plan:** file an xarray issue with the repro above. (Related to item 1: both are
`CoordinateTransformIndex` selection gaps.)

## 3. (add future ideas here)
