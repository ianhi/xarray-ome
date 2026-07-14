# RangeIndex

`RangeIndex` (experimental) is the xarray index that matches NGFF most exactly: it represents a 1-D affine coordinate `scale * i + translation`, storing only the parameters rather than a dense array. NGFF per-axis `scale`+`translation` *is* this, so `RangeIndex` is the natural lazy representation of a physical axis coordinate.

## How it works

It stores `start`, `stop`, and `size` (the step is derived, which is why equality uses `np.isclose`), and generates coordinate values on demand. Constructors mirror NumPy:

```python
from xarray.indexes import RangeIndex
idx = RangeIndex.arange("x", start=0.0, step=0.5, size=2048, dim="x")   # 0, 0.5, 1.0, …
# or RangeIndex.linspace(...) for endpoint-based construction
```

1-D `slice` selection is lossless and parameter-preserving: `isel(x=slice(10, 20))` and `sel(x=slice(5.0, 10.0))` return a *new* `RangeIndex` with updated `start`/`size`, never materialising the array. This is exactly the behaviour we want when cropping a level.

## The caveats that keep it opt-in

For our use case the experimental edges matter:

- **`from_variables` deliberately raises `NotImplementedError`** — a `RangeIndex` must be built from parameters, not inferred from a dense coordinate. So the custom backend reconstructs it from the carrier's transform parameters on open, not from stored coordinate values.
- **`sel` is nearest-only, with no tolerance.** Point selection snaps to the closest pixel; there is no `method=`/`tolerance=` story yet.
- **Fancy (non-slice) `isel` materialises a `PandasIndex`**, dropping the lazy representation.
- **Custom indexes are not serialised** by the Zarr backend — another reason the backend rebuilds the index rather than relying on persistence.

The first two — nearest-only `sel` and no label slices — are why the mapping does **not** use `RangeIndex` directly: it subclasses `CoordinateTransformIndex` instead, overriding `sel` to add world-unit scalar/slice/bbox selection ([](../mapping/transforms-to-coords.md), [](../mapping/custom-index-design.md)). The serialisation gap is handled the same way for either index: the backend rebuilds from carrier parameters on open.

:::{seealso}
- [](../spec/coordinate-transformations.md) — the `scale`/`translation` this represents
- [](coordinate-transform-index.md) — the N-D generalisation
- [](../mapping/custom-index-design.md) — how the backend would attach and rebuild it
:::
