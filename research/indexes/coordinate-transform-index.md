# CoordinateTransformIndex

`CoordinateTransformIndex` (experimental) wraps a `CoordinateTransform` — an object with `forward` (grid → world) and `reverse` (world → grid) maps — to produce **lazy, possibly N-D** coordinates. Where [](range-index.md) handles the 1-D affine case, this is the general mechanism — and it is both what `xarray_ngff` builds on **today** (via its `TransformIndex` subclass) and what will carry NGFF's future (RFC-5 affine/non-separable transforms).

## How it works

`CoordinateTransform` defines `forward`/`reverse` over named dimensions; `CoordinateTransformIndex` uses them to generate coordinate variables lazily (via an indexing adapter whose values are computed, never stored — `_in_memory=False`). One transform can back **several** coordinate variables at once, which is the meta-index pattern for a transform that spans multiple axes:

```python
coords = Coordinates.from_xindex(CoordinateTransformIndex(transform))
ds = ds.assign_coords(coords)
```

`sel` is supported through `reverse()`.

## Maturity and limits

- Generic N-D `sel` is **point-wise nearest-only** — no slice selection in the N-D case.
- N-D `isel` returns `None`, i.e. it **drops the index**.
- Alignment is **exact-only**.
- Like all custom indexes, it is **not serialised**; the backend reconstructs it.

## Relevance to NGFF

For NGFF 0.5 — diagonal `scale`+`translation` — `RangeIndex` looks like the natural per-axis fit, but its `sel` is nearest-only and cannot resolve label slices. `xarray_ngff` therefore builds on `CoordinateTransformIndex` instead, in a `TransformIndex` subclass that overrides `sel` for scalar, inclusive slice, and N-D bounding-box selection in world units ([](../mapping/custom-index-design.md)). The same mechanism carries forward to non-separable transforms (affine, rotation) when NGFF RFC-5 lands; such transforms are preserved verbatim in the carrier ([](../mapping/round-trip.md)) until the spec and reader support surfacing them as coordinates.

:::{seealso}
- [](range-index.md) — the 1-D case we actually use today
- [](../mapping/transforms-to-coords.md) — why dense + carrier, not this, for now
- [](../spec/coordinate-transformations.md) — current vs. future transform types
:::
