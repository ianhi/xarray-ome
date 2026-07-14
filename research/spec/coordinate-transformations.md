# Coordinate Transformations

NGFF `coordinateTransformations` describe how discrete array indices map to physical coordinate space. They are the bridge between "voxel 42 along `x`" and "4.2 µm from the origin" — and they are the NGFF field most directly responsible for the physical meaning of the data. Everything in the xarray mapping that touches *coordinates* (as opposed to raw arrays) ultimately comes from here.

## The three transform types

NGFF 0.5 defines exactly three transform types (see {ref}`coordinate-transformations-metadata` in the spec):

| type | fields | meaning |
|---|---|---|
| `identity` | — | no change; default |
| `translation` | `"translation": [float, ...]` | add a per-axis offset |
| `scale` | `"scale": [float, ...]` | multiply per-axis by a factor |

`translation` and `scale` MAY alternatively carry `"path": str` pointing at binary data inside the store rather than inline floats. This is uncommon in practice — almost every OME-Zarr in the wild stores transforms inline — but a full round-trip must preserve the `path` form when it appears.

## Composition rules

Transforms appear in a **list** and are applied sequentially. The spec is explicit about order inside the `datasets[].coordinateTransformations` list:

> They MUST contain exactly one `scale` specifying pixel size in physical units. […] MAY contain exactly one `translation`. If `translation` is given it MUST be listed after `scale`.

So per-dataset the pattern is fixed: `scale` first, optional `translation` second. This matches the natural interpretation — scale the integer grid to physical units, then shift.

## Two layers of transforms

A subtlety: the `multiscales` object carries transforms in **two places**:

1. **Per-dataset** (`multiscales[].datasets[].coordinateTransformations`) — required, one per resolution level.
2. **Global** (`multiscales[].coordinateTransformations`) — optional, applied *after* per-dataset transforms, shared across all levels.

From the spec example:

```json
"datasets": [
  { "path": "0", "coordinateTransformations": [{"type": "scale", "scale": [1.0, 1.0, 0.5, 0.5, 0.5]}] },
  { "path": "1", "coordinateTransformations": [{"type": "scale", "scale": [1.0, 1.0, 1.0, 1.0, 1.0]}] },
  { "path": "2", "coordinateTransformations": [{"type": "scale", "scale": [1.0, 1.0, 2.0, 2.0, 2.0]}] }
],
"coordinateTransformations": [
  { "type": "scale", "scale": [0.1, 1.0, 1.0, 1.0, 1.0] }
]
```

The effective transform for an element at integer index `i` on axis `a` in level `L` is:

```
physical(a, i, L) = global_transform( per_dataset_transform_L( i ) )
```

For the example above, a time-axis (`t`) element at index `i` in level 0 has physical coordinate `0.1 * (1.0 * i) = 0.1 * i` seconds.

## What physical coordinates look like

For a `scale`-only transform `s` on an axis of length `N`, the physical coordinates are:

```
coords = s * arange(N)
```

Adding a `translation` `t` shifts to:

```
coords = t + s * arange(N)
```

These are 1-D, evenly spaced, and fully determined by two scalars. That is the critical property that makes a **lazy** representation possible — we do not need to store `N` floats per axis; we need to store `(s, t)` and a length.

## The redundancy problem

The spec *requires* a per-dataset `scale` on every level, including when it is the no-op `[1, 1, 1, 1, 1]`. Relative-to-highest-resolution is also permitted ("If scaling info is not available for an axis, the value MUST express the scaling factor between the current resolution and the first resolution, defaulting to 1.0."). This means one multiscale group can legitimately encode the same pyramid in two styles:

- **Absolute style:** each level's per-dataset scale is the physical pixel size at that level; no global transform.
- **Relative style:** each per-dataset scale is relative downsampling vs. level 0; the global transform carries the absolute pixel size.

Both are valid and observable in published data. The xarray mapping must produce the same physical coordinates either way — which is natural if we always compose global ∘ per-dataset.

## Edge cases worth naming

- **`"path"` forms of scale/translation.** Binary data in the store; rare but spec-valid. Round-trip must preserve the reference, not materialize it into attrs.
- **Floating-point drift.** If we materialize coords eagerly (`t + s * arange(N)`), recovering `(s, t)` from the values on write requires care. `spatialdata` has reported this as a real source of bugs. See [](../prior-art.md) § spatialdata.
- **Channel and time axes.** The spec allows `scale[c]` and `scale[t]` (the example has `scale: [0.1, 1.0, ...]` for `t`). Channel coords as floats are meaningless; time is fine. The mapping resolves this: the channel coordinate is the omero labels, not `scale[c]` (see [](../mapping/omero-to-coords.md)); `scale[c]` is preserved in the carrier.

## Questions this raised (resolved in the mapping)

1. **Eager vs. lazy coordinates.** Materialize `t + s * arange(N)` as a concrete coord array, or wrap `(s, t, N)` in a custom index like [](../indexes/range-index.md) or [](../indexes/coordinate-transform-index.md)? The lazy path is cheaper and round-trips exactly; the eager path is simpler for downstream xarray users who expect plain coords.
2. **Where does the transform live on write?** If we take the eager path, we must either recover `(s, t)` from coord values (hazardous) or stash the originals in `attrs` and trust them on write.
3. **Global vs. per-dataset on write.** When generating NGFF from an xarray DataTree, which style do we emit? (Probably: absolute per-dataset, empty global — the simpler form to parse.)

These questions are taken up in [](../mapping/transforms-to-coords.md).

:::{seealso}
- [](axes.ipynb) — axes define the coordinate space; transforms operate on it
- [](multiscales.md) — the `datasets` array that hosts per-level transforms
- [](../mapping/transforms-to-coords.md) — the mapping decision for this spec topic
- [](../indexes/range-index.md), [](../indexes/coordinate-transform-index.md) — candidate lazy representations
:::
