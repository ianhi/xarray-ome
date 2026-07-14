# Transforms → Coords

`coordinateTransformations` are where the *physical meaning* of the data enters xarray. The spec side is covered in [](../spec/coordinate-transformations.md); this page describes how a transform becomes an xarray coordinate, why we expose it *and* keep the original, and how this interacts with the multiscale pyramid. It reflects what the `xarray_ngff` reference implementation actually does.

```{admonition} Recommendation
:class: tip
1. **Expose each axis's physical coordinate lazily**, backed by a `TransformIndex` (a `CoordinateTransformIndex` subclass) that stores only the parameters `(scale, translation)` and computes `translation + scale · arange(N)` on access — no dense array is stored.
2. The index provides **world-unit `.sel`** — scalar, inclusive (sign-agnostic) label slice, and N-D bounding box — resolved through the transform's inverse, so `da.sel(x=4.2)` and `da.sel(x=slice(0, 10))` work in physical units.
3. **Preserve** the raw `coordinateTransformations` verbatim in the round-trip carrier ([](round-trip.md)). On write, emit transforms **from the carrier** — never reverse-engineer `(scale, translation)` from coordinate values.
4. Coordinates are **local to each resolution level** (each DataTree node), computed by composing `global ∘ per-dataset`.
5. **Do not** materialise a channel-axis coordinate from `scale[c]`; the channel coordinate is the omero labels ([](omero-to-coords.md)).
```

## From transform to coordinate

For a per-axis scale `s` and translation `t` on an axis of length `N`, the physical coordinate is fully determined by three numbers:

```python
coord = t + s * np.arange(N)        # 1-D, evenly spaced
```

The reference implementation does **not** store that array. It attaches a `TransformIndex` that holds `(s, t)` and produces the values on demand (`xarray_ngff.indexes.transform_coords`), so the coordinate behaves like a plain evenly-spaced coordinate while storing only three numbers.

NGFF places transforms in two layers — required per-dataset (per level) and an optional global transform applied after (see [](../spec/coordinate-transformations.md)). We always compose them the same way, which makes the two legal encodings (absolute per-level scales vs. relative scales + a global absolute scale) produce identical coordinates:

```python
physical(axis, i, level) = global_transform(per_dataset_transform[level](i))
```

This is the *happy path*: NGFF 0.5 only has diagonal `scale` + `translation`, both of which are exactly represented by the affine transform the index stores.

## Why expose a coordinate (not the transform alone)

The competing approach — `SpatialData`'s — stores the transform graph and **does not** put physical coordinates on the array at all ([](../prior-art.md)). For our scope, exposing a real coordinate wins on two counts:

- **Ergonomics.** `da.sel(x=4.2)` selects by micrometre only if `x` is a real coordinate. Downstream xarray users expect plain coordinates; a bare integer grid with the scale hidden in metadata is the thing every other reader (including `bioio`) forces users to work around.
- **Multiscale selection falls out for free.** This is the decisive point. `DataTree.sel` resolves the *same physical label range* against each level's own coordinate, so a single `tree.sel(y=slice(0, 10))` returns the correct pixels at *every* resolution (verified: 4 px @ 1 µm and 2 px @ 2 µm for the same 0–4 µm span). With transform-only storage there is nothing for `.sel` to resolve against, and — because selection cannot propagate across DataTree nodes via an index ([](../indexes/index-overview.md)) — a per-level coordinate is what makes cross-level selection work at all.

Crucially, exposing a coordinate does **not** require a dense array: the `TransformIndex` gives the ergonomics and cross-level selection above while storing only the parameters.

## Why *also* preserve the raw transform — and never invert the coordinates

The coordinate (whether dense or index-backed) is a **derived, read-optimised view**, not the source of truth. On write we emit transforms from the preserved originals, for three reasons:

- **`path` forms.** `scale`/`translation` may reference binary data in the store rather than inline floats. These must round-trip *by reference*; they were never materialisable into a coordinate.
- **Forward compatibility.** A future transform (affine/rotation via NGFF RFC-5) is not a simple per-axis `(scale, translation)`. The carrier preserves it verbatim even when the reader does not surface it as a coordinate.
- **Exactness and unknown fields.** Re-deriving `(s, t)` by differencing a coordinate array accumulates floating-point error (a documented source of bugs in `SpatialData`). The index already holds the exact parameters, and the carrier holds everything else, so the write never has to guess.

So the contract is: **the coordinate for working with the data; the carrier for writing it back.** `bioio-ome-zarr`'s eager-only approach — which drops units, ignores translation, and discards `path` forms — is precisely the lossy outcome this split avoids.

## Coordinates are per-level (local), not inherited

In a DataTree pyramid each level has differently-sized `y`/`x` with different physical coordinates. xarray's coordinate **inheritance aligns child against parent with `join="exact"`**, so a `y`/`x` coordinate placed on the root *collides* with every downsampled level (a `ValueError`). The rule, developed in [](multiscales-to-datatree.md):

- downsampled spatial coordinates (`z`/`y`/`x`) are **local** to each level node;
- only genuinely shared axes (`c`, `t`, whose length is constant across levels) may live on the root and be inherited.

## The lazy index we ship

The coordinate is backed by `TransformIndex`, a subclass of xarray's `CoordinateTransformIndex`. It stores the affine parameters and adds the world-unit selection the base class lacks:

- **scalar** — `da.sel(x=4.2)` maps the label to a pixel via the transform's inverse, rounds, and clips to the axis extent;
- **label slice** — `da.sel(x=slice(2.0, 8.0))` is inclusive and sign-agnostic (handles descending axes);
- **N-D bounding box** — a slice per world axis selects the covering pixel tile, resolved through the inverse (a *superset* for warped transforms).

This is why we do **not** use xarray's stock `RangeIndex`, whose limitations the earlier design cited: its `sel` is nearest-only and `from_variables` raises. `TransformIndex` addresses selection directly, and the separate xarray bug that once broke reducing a transform-backed axis to length 1 (single z-slice / timepoint) is fixed as of xarray 2026.1.0 (our floor) — so a lazy coordinate is now a safe default, not a future aspiration.

Two properties follow from using a custom index, both handled by the design:

- **Custom indexes are not serialised.** The backend reconstructs the index from the (carrier-preserved) parameters on open — there is nothing to persist beyond the transforms already in the store.
- **It generalises.** The same machinery expresses a general N-D affine (`AffineTransform`, with an exact matrix inverse) and even non-affine invertible transforms — the path toward RFC-5 coordinate systems, which dense 1-D arrays cannot represent at all. See [](../indexes/coordinate-transform-index.md) and [](custom-index-design.md).

## Channel and time axes

The spec permits `scale[c]` and `scale[t]`. A floating-point physical coordinate is meaningful for `t` (surface it normally) but **not** for `c` — a channel index is categorical. So the channel axis's coordinate is the omero **labels**, not a value derived from `scale[c]` ([](omero-to-coords.md)). We still preserve `scale[c]` in the carrier so the write is faithful; we just don't surface it as the channel coordinate.

## On write

When generating NGFF from an xarray DataTree we emit the **simplest valid form**: an absolute per-dataset `scale` (plus a `translation` if present) on each level and an empty global transform — taken from the carrier, not re-derived. `path`-form transforms are written back by reference.

## Rejected alternatives

- **Transform-only, no coordinate on the array** (`SpatialData`). Rejected for our scope: it sacrifices `.sel` ergonomics and free multiscale selection. Its motivation — affine/rotation and heterogeneous non-raster elements — is real but does not apply to NGFF 0.5 images, which are diagonal scale + translation.
- **Eager-only, transform discarded** (`bioio-ome-zarr`). Rejected by requirement #1: it drops units, ignores translation, loses `path` forms, and forces hazardous coordinate inversion on write.
- **A dense stored coordinate array.** A viable, simpler variant that behaves identically for the user — but it costs memory on large axes, and (if used as the write source) invites the differencing drift above. Since the `TransformIndex` gives the same ergonomics while storing only parameters and extending to N-D transforms, the lazy index is the better default. Dense remains a legitimate fallback where a custom index is undesirable.
- **xarray's stock `RangeIndex` as-is.** Rejected: `from_variables` raises and `sel` is nearest-only. The purpose-built `TransformIndex` subclass avoids both.

:::{seealso}
- [](../spec/coordinate-transformations.md) — the transform types, composition rules, and `path` forms
- [](axes-to-dims.md) — the axis coordinate is also the home for `type`/`unit`
- [](multiscales-to-datatree.md) — why per-level coordinates must be local
- [](omero-to-coords.md) — why the channel axis uses labels, not `scale[c]`
- [](round-trip.md) — the carrier that holds the original transforms
- [](../indexes/coordinate-transform-index.md), [](custom-index-design.md) — the lazy index this ships
:::
