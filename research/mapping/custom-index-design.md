# Custom Index Design

[](transforms-to-coords.md) ships each physical coordinate as a **lazy, transform-backed index**. This page describes that index as implemented in `xarray_ngff.indexes` — what it is, what it does on today's xarray, and the two upstream caveats the backend works around.

```{admonition} Recommendation
:class: tip
1. The coordinate is backed by `TransformIndex`, a subclass of xarray's `CoordinateTransformIndex`, that stores the affine parameters `(scale, translation)` per axis and computes values on demand — not a dense array, and **not** `RangeIndex` (whose `sel` is nearest-only and whose `from_variables` raises).
2. `TransformIndex` overrides `sel` to add **world-unit selection** the base class lacks: scalar, inclusive sign-agnostic label slice, and N-D bounding box, all resolved through the transform's `reverse`.
3. The custom backend **reconstructs the index on open** from the carrier's transform parameters — custom indexes are not serialised, and there is nothing to persist beyond the transforms already in the store.
4. **Do not** put cross-level multiscale logic in the index; that is structurally an accessor concern.
```

## Why an index, not a dense array

A `scale`+`translation` coordinate on an axis of length `N` is fully determined by two scalars, yet a dense coordinate stores `N` floats per axis per level. For a deep pyramid of large images that is wasteful, and — more subtly — re-deriving `(scale, translation)` from the dense values on write invites floating-point drift ([](transforms-to-coords.md)). An index that *keeps the parameters* avoids both: it is cheaper and it round-trips exactly. It also generalises to transforms a 1-D array cannot express at all (N-D affine, and beyond).

xarray already ships the mechanism. `CoordinateTransform`/`CoordinateTransformIndex` wrap `forward` (grid → world) and `reverse` (world → grid) maps to produce lazy, possibly N-D coordinates. `xarray_ngff` specialises this rather than inventing a new mechanism.

## What we build on it

From `xarray_ngff.indexes`:

- **`AffineCoordinateTransform`** — the 1-D `phys = scale · pixel + translation` map for one axis.
- **`AffineTransform`** — a general N-D affine `world = A @ pixel + t` with an exact matrix inverse (no KD-tree), the path toward RFC-5 coordinate systems.
- **`TransformIndex`** — the `CoordinateTransformIndex` subclass that adds world-unit `sel`.
- **`transform_coords(sizes, scale, translate)`** — builds the lazy coordinates a reader attaches, one `TransformIndex` per axis.

`TransformIndex.sel` recognises three modes: **scalar** (map → round → clip to `[0, size-1]`), **bounding box** (any `slice` label → covering pixel tile via `reverse`; the 1-D case is an inclusive, sign-agnostic label slice), and **point-wise** (`DataArray`/`Variable` labels delegate to the base class). The bbox is a *superset* for warped transforms — the returned tile contains the requested world region.

## Upstream caveats, and how the backend handles them

Two properties of custom indexes remain, both handled by the design rather than blocking it:

| property | how it's handled |
|---|---|
| custom indexes are **not serialised** by a plain `to_zarr` | the backend rebuilds the index on open from the carrier's transform parameters (there is nothing extra to store) |
| `CoordinateTransformIndex.from_variables` raises | irrelevant to us — the index is constructed from parameters, not from coordinate values |

The selection limits that once argued *against* a lazy default — `sel` being nearest-only, no label slices — are exactly what `TransformIndex.sel` overrides, and the separate xarray bug that broke reducing a transform-backed axis to length 1 is fixed as of xarray 2026.1.0. The scalar/slice/bbox `sel` logic is general enough to be a candidate upstream contribution to `CoordinateTransformIndex` itself (see `notes/upstream-ideas.md`).

## The thing the index must *not* do

It is tempting to make the index link resolution levels so that selecting on the full-res level narrows the others. The index machinery forbids this: `IndexSelResult` cannot reach beyond its own object and `DataTree.sel` indexes each node independently ([](multiscales-to-datatree.md)). Cross-level logic therefore lives in the **accessor**, not the index — and ordinary per-level `sel` already resolves physical labels correctly.

## The dense fallback

A plain dense coordinate array is behaviourally identical to the user (`da.sel(x=4.2)`, `da["x"]`, physical units in the repr) and remains a legitimate choice where a custom index is undesirable. The reference implementation ships the lazy index because it stores parameters exactly, is cheap on large axes, and extends to N-D transforms; dense is the simpler variant, not the recommendation.

:::{seealso}
- [](../indexes/range-index.md) — xarray's 1-D `scale`+`translation` index, and why we don't use it directly
- [](../indexes/coordinate-transform-index.md) — the general N-D transform wrapper `TransformIndex` subclasses
- [](../indexes/index-overview.md) — the `Index` contract and why selection can't cross objects
- [](transforms-to-coords.md) — how the coordinate is produced and written back
- [](round-trip.md) — the carrier the index is reconstructed from on open
:::
