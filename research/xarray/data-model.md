# xarray Data Model

This appendix maps *where metadata can live in xarray* and *what survives which operation* — the basis for where each NGFF field is placed in the proposal. (Findings here are grounded in the xarray source; see `notes/field-research/xarray-data-model-surface.md`.)

## The containers

- **`Variable`** — the array wrapper: dimensions, values, `attrs`, `encoding`.
- **`DataArray`** — a named `Variable` plus its coordinates.
- **`Dataset`** — a dict-like collection of aligned variables sharing dimensions, with its own `attrs`.
- **`DataTree`** — a tree of named groups, each wrapping a Dataset ([](datatree.md)).

## Where metadata can live

| location | holds | visible in repr | indexable by `.sel` |
|---|---|---|---|
| **dimension name** | the axis identity | yes | — |
| **dimension coordinate** | 1-D labels along a dim (the physical coordinate, channel labels) | yes | **yes** |
| **non-dimension coordinate** | auxiliary labels (scalar or N-D) | yes | **no** (silent no-op) |
| **coordinate `attrs`** | per-coordinate metadata (`units`, `axis_type`) | partially | — |
| **variable / Dataset `attrs`** | free-form metadata | partially | — |
| **`encoding`** | storage mechanics only | no | — |

Two of these rows carry the gotchas that shape the mapping.

### Coordinates: dimension vs. non-dimension

A **dimension coordinate** shares its name with a dimension and indexes it — this is what makes `da.sel(c="DAPI")` work. A **non-dimension coordinate** is just labelled data; crucially, **`.sel()` on a non-indexed coordinate is a silent no-op** (it returns the full array, no error). This is why channel labels must be the `c` *dimension* coordinate ([](../mapping/omero-to-coords.md)), not an auxiliary one. Scalar (0-d) and N-D coordinates are legal and round-trip through Zarr, but they do not provide selection.

### attrs: durable, but with named exceptions

The folklore "xarray drops attrs" is **out of date and must be stated precisely**, because the axes decision depends on it:

- **Preserved by default:** reductions (`.mean()`), elementwise/unary ops, and slicing all keep `attrs` (`_get_keep_attrs(default=True)`).
- **Lost in narrow cases:** binary ops between objects with *conflicting* values for a key; `merge`/`concat` (which default to keeping only the first object's attrs); explicit `keep_attrs=False`.
- **Durable on disk:** Dataset/variable/coordinate `attrs`, including nested dicts and lists, round-trip losslessly through the Zarr v3 backend (they must be JSON-serialisable).

The practical lesson: putting `units`/`axis_type` on a **coordinate** (rather than the data variable or the Dataset) keeps them attached through the operations that matter and out of the way of the merges that drop them — the same reasoning `rioxarray` uses for CRS.

### CF "magic" attrs to avoid colliding with

xarray's own CF decoding intercepts certain attr keys on read and *moves them into `encoding`*: `_FillValue`, `scale_factor`/`add_offset`, time `units`+`calendar`, `coordinates`, `grid_mapping`. A spatial `units` like `"micrometer"` is inert to xarray (safe, unused). We deliberately reuse `units` for interop but avoid naming any domain field after the magic keys.

:::{seealso}
- [](encoding.md) — why the `encoding` dict is the one genuinely unsafe surface
- [](datatree.md) — the hierarchical container for multiscale data
- [](../mapping/axes-to-dims.md) — applying this to axis `type`/`unit`
- [](../mapping/omero-to-coords.md) — applying the dimension-coordinate rule to channel labels
:::
