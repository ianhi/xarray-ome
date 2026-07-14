# DataTree

`DataTree` is xarray's hierarchical container: a tree of named groups, each wrapping a Dataset, with optional coordinate inheritance between a node and its ancestors. It is the target for NGFF multiscale pyramids. This page documents the behaviours that matter for that mapping (grounded in the xarray source and experiments; see `notes/field-research/xarray-datatree-deep.md`).

## Nodes and names

Each node is a named group holding one Dataset's variables plus its children. A node name forbids only `/` and non-strings, so numeric NGFF dataset paths (`"0"`, `"1"`) are *legal* names — we rename them to `scale0`, `scale1` purely for ergonomics. `DataTree.name` on the root carries the NGFF multiscale `name`.

Sibling nodes **may differ** in dimensions, sizes, and coordinates — exactly what a pyramid needs. The alignment constraint is *vertical only* (a node against its ancestors), never between siblings.

## Coordinate inheritance — and how it fights pyramids

Coordinates (and their indexes) can be inherited from a parent via a ChainMap. But **every attach runs `align(node, parent, join="exact")`**. That has a sharp consequence for pyramids: a `y`/`x` coordinate placed on the root will *fail to align* with any downsampled child (different length → `ValueError`).

The rule this forces:

- coordinates whose length is **constant** across levels (`c`, `t`) may live on the **root** and be inherited;
- coordinates that **shrink** per level (`z`, `y`, `x`) must be **local** to each level node.

So inheritance is genuinely useful — for the channel/time coordinates and their attrs — but the spatial coordinates that define the pyramid cannot be inherited. (`attrs`, unlike coordinates, are **not** inherited at all; each node has its own.)

## Selection across the tree

`DataTree.sel`/`isel` broadcast to every node and silently skip nodes that lack the named dimension. For a pyramid:

- **`sel` by physical label is correct** — each level resolves the same label range against *its own* coordinates, so one `tree.sel(y=slice(0, 10))` yields the right pixels at every resolution.
- **`isel` by integer is wrong** — the same integer means a different physical location at each level.

There is no channel for one node's selection to influence another; cross-node logic is not possible through indexing ([](../indexes/linked-indexes.md)).

## Zarr persistence

Node ↔ Zarr group, variable ↔ array, node `attrs` ↔ `zarr.json["attributes"]` (nested dicts round-trip verbatim). This lines up with NGFF, which stores `multiscales` on the *parent group* whose children are the scale arrays — so the backend writes `attributes.ome` onto the root node. Two rough edges the custom backend must handle: a DataTree leaf is always a group (so a level array lands at `scale0/<var>`, not bare `scale0`), and `to_zarr(group=...)` is unimplemented while v3 consolidated metadata warns.

:::{seealso}
- [](../mapping/multiscales-to-datatree.md) — the multiscale mapping built on these behaviours
- [](data-model.md) — coordinates, dimension vs. non-dimension, attrs durability
- [](../mapping/round-trip.md) — writing `attributes.ome` back onto the group
:::
