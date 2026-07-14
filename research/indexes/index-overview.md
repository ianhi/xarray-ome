# Index Overview

An xarray **index** is the object behind label-based selection, alignment, and lazy coordinate generation. Understanding its contract — and its hard limits — decides what the NGFF transform mapping can and cannot push into an index versus the accessor. (Grounded in the xarray source; see `notes/field-research/xarray-indexes-deep.md`.)

## The `Index` contract

The `Index` base class exposes ~15 methods, but **only `from_variables` is required**; the rest are optional and, when absent, either raise or cause the index to be silently dropped for that operation. The notable ones:

- `from_variables` — build the index from coordinate variables (required).
- `create_variables` — produce the (possibly lazy) coordinate variables the index backs.
- `sel` — turn a label query into positional indexers, returning an `IndexSelResult`.
- `isel`, `equals`, `join`, `reindex_like`, `rename`, `concat`, `stack`/`unstack` — optional participation in the rest of xarray's machinery.

`PandasIndex` is the complete reference implementation and the default for a 1-D dimension coordinate; it materialises all labels in memory (a pandas `Index`).

## The hard limit: selection cannot cross objects

`sel` returns an `IndexSelResult`, whose fields apply positional indexers to the **existing variables of the same object**. It **cannot** change the backing array, add dimensions, or reference another object — and `merge_sel_results` *raises* if two indexes try to drive the same dimension. Within one Dataset an index *can* propagate a selection on one coordinate to several dimensions (the meta-index / `NDPointIndex` pattern). **Across DataTree nodes it cannot**: `DataTree.sel` indexes each node independently with no inter-node channel.

This single fact settles a recurring design question: multiscale cross-level selection ([](../mapping/multiscales-to-datatree.md)) is **not** expressible as an index and must live in the accessor.

## Why custom indexes for NGFF

The default `PandasIndex` works but materialises every coordinate value. NGFF's `scale`+`translation` coordinates are fully described by two scalars, so a custom index can store the *parameters* and compute values lazily — cheaper, and exact on round-trip (no float drift). The candidates:

- [](range-index.md) — the 1-D `scale * i + translation` case (NGFF's exact shape);
- [](coordinate-transform-index.md) — the general N-D `forward`/`reverse` wrapper;
- [](linked-indexes.md) — cross-*dimension* propagation within one object (and why it stops at the DataTree boundary).

The mapping ships the lazy, transform-backed coordinate — a `CoordinateTransformIndex` subclass — as its default ([](../mapping/custom-index-design.md)).

:::{seealso}
- [](range-index.md), [](coordinate-transform-index.md), [](linked-indexes.md)
- [](../mapping/custom-index-design.md) — the prototype OME index
- [](../mapping/transforms-to-coords.md) — dense default vs. lazy index
:::
