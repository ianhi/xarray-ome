# Multiscales

The `multiscales` field is the entry point into an OME-Zarr image. It lives in the group-level `zarr.json` (under the `ome` namespace) and describes a **resolution pyramid**: a set of arrays holding the same image at progressively coarser resolutions, sharing axes and related by coordinate transformations.

This page covers the JSON structure, the fields that matter for the xarray mapping, and the subtleties that make multiscales harder than "a list of arrays."

## The JSON structure

From {ref}`multiscales-metadata`, a minimal example looks like:

```json
{
  "attributes": {
    "ome": {
      "version": "0.5",
      "multiscales": [
        {
          "name": "example",
          "axes": [
            { "name": "t", "type": "time",    "unit": "millisecond" },
            { "name": "c", "type": "channel" },
            { "name": "z", "type": "space",   "unit": "micrometer" },
            { "name": "y", "type": "space",   "unit": "micrometer" },
            { "name": "x", "type": "space",   "unit": "micrometer" }
          ],
          "datasets": [
            { "path": "0", "coordinateTransformations": [{"type": "scale", "scale": [1, 1, 0.5, 0.5, 0.5]}] },
            { "path": "1", "coordinateTransformations": [{"type": "scale", "scale": [1, 1, 1.0, 1.0, 1.0]}] },
            { "path": "2", "coordinateTransformations": [{"type": "scale", "scale": [1, 1, 2.0, 2.0, 2.0]}] }
          ],
          "coordinateTransformations": [
            { "type": "scale", "scale": [0.1, 1, 1, 1, 1] }
          ],
          "type": "gaussian",
          "metadata": { "method": "skimage.transform.pyramid_gaussian" }
        }
      ]
    }
  }
}
```

Two structural facts to internalize:

1. **`multiscales` is a list.** A single Zarr group may contain multiple multiscale images. In practice it almost always has length 1, but a round-tripping mapping must not assume that.
2. **`axes` lives at the multiscale level, not the dataset level.** All resolution levels share the same axes; they differ only in shape and per-dataset transforms.

## Required and optional fields

Inside each `multiscales` entry:

| field | req. | what it is |
|---|---|---|
| `axes` | MUST | 2–5 entries; ordering: time, then channel/custom, then 2–3 space. See [](axes.ipynb). |
| `datasets` | MUST | list of resolution levels, **ordered largest → smallest**. |
| `datasets[].path` | MUST | relative path to the Zarr array for this level. |
| `datasets[].coordinateTransformations` | MUST | exactly one `scale`, optional trailing `translation`. See [](coordinate-transformations.md). |
| `coordinateTransformations` | MAY | global transforms applied after per-dataset. |
| `name` | SHOULD | human-readable name of the image. |
| `type` | SHOULD | downscaling method used to produce the pyramid (free string, e.g. `"gaussian"`). |
| `metadata` | SHOULD | arbitrary object describing the downscaling method. |

There is no `version` *inside* a `multiscales` entry — the version lives once at the top of the `ome` namespace (`"version": "0.5"`). Older spec versions carried a per-entry version; 0.5 dropped it.

## Ordering constraints

The spec enforces ordering in two places:

- **`axes` order by type:** time (if present) → channel/custom (if present) → space. For 3-D anisotropic space, `zyx` is recommended.
- **`datasets` order by resolution:** largest first, smallest last. Index `0` is the full-resolution level.

These constraints show up in the xarray mapping as invariants: if we iterate `datasets` in order, the DataTree's first child is level 0, and the dim order of every level is the axes order.

## What the `datasets` list is for

Each entry points at a separate Zarr array. The arrays share dtype and axes but differ in shape. Two implementations of "a pyramid":

- The **absolute** style: every per-dataset `scale` is the physical pixel size at that level. No global transform.
- The **relative** style: per-dataset `scale` encodes downsampling vs. level 0 (usually `[1,1,1,1,1]` at level 0, then `[1,1,2,2,2]`, `[1,1,4,4,4]`, …). The absolute pixel size lives in the global `coordinateTransformations`.

Both are valid. See [](coordinate-transformations.md) § "The redundancy problem" for why this matters.

## Where the fields end up in xarray

Informal preview of the mapping (full detail in [](../mapping/multiscales-to-datatree.md)):

| NGFF field | xarray location |
|---|---|
| `multiscales[i].name` | `DataTree.name` of the image root |
| `multiscales[i].axes` | dim names on every array; type/unit on coord attrs (see [](axes.ipynb)) |
| `multiscales[i].datasets` | one `DataTree` child per entry, in order |
| `datasets[j].path` | the child's name (typically `"0"`, `"1"`, …) |
| `datasets[j].coordinateTransformations` | coords (or a custom index) on the child |
| `multiscales[i].coordinateTransformations` | composed into each child's coords |
| `type`, `metadata` | attrs on the root node |

The deliberate gap: **nothing in the spec identifies which axis is "resolution."** The pyramid is a tree structure, not an extra dimension. That is why DataTree is the natural container and a flat Dataset with a `level` dim is not — levels differ in *shape*, and xarray dims cannot be ragged.

## Edge cases worth naming

- **Multiple multiscale images per group.** Length-`>1` `multiscales` list. How does the DataTree root represent this? Separate child per entry, keyed by `name`?
- **Missing `name`.** Spec says SHOULD, not MUST. Mapping must tolerate absence and choose a sensible fallback (we are currently using `DataTree.name` from the path, per commit [`4203ed7`](https://github.com/ianhi/xarray-ngff/commit/4203ed7)).
- **Heterogeneous level dtypes.** Not strictly forbidden by the spec. Producers in practice keep dtype constant; readers probably should not assume it.
- **Transforms that differ only by translation.** Some producers fix `scale` across levels and encode downsampling in `translation`. Unusual but spec-legal.
- **`type` and `metadata` are free-form.** Pure passthrough in both directions.

## Questions this raised (resolved in the mapping)

1. **Multiple multiscales in one group.** The DataTree structure needs to accommodate it even if it is rare. One proposal: when `len(multiscales) > 1`, each entry becomes a named child of the group root.
2. **Relative-style transforms on write.** Do we emit absolute (simpler to read) or relative (canonical for producers like `ome-zarr-py`)? Is there value in detecting which style was read and preserving it?
3. **`type` + `metadata` pass-through.** These are producer-specific. They should survive attrs with no interpretation.

These are resolved in [](../mapping/multiscales-to-datatree.md).

:::{seealso}
- [](axes.ipynb) — the shared axes that anchor every level
- [](coordinate-transformations.md) — what lives inside each `datasets` entry
- [](../mapping/multiscales-to-datatree.md) — the DataTree mapping
:::
