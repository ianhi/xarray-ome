# Linked Indexes

The [xarray-linked-indexes](https://github.com/xarray-contrib/xarray-linked-indexes) experiments explore indexes that propagate a selection from one coordinate to *another* — `DimensionInterval` (a selection on one dimension narrows a related one) and `NDIndex` (N-D coordinates derived from shared parameters). It is tempting to reach for this pattern for multiscale data: select a region at full resolution and have the coarser levels follow. This page explains why that intuition is **half right**, and where the boundary is.

## What linked indexes *can* do

Within a **single** Dataset, an index can legitimately drive multiple dimensions from one query. This is real and shipping: the built-in `NDPointIndex` resolves a point against an N-D coordinate, and the linked-indexes `NDIndex`/`MultiIntervalIndex` propagate a selection across dimensions of the same object. So *within one resolution level*, cross-dimension coupling is possible.

## Where it stops: the DataTree boundary

The multiscale use case needs something the machinery does not allow. A selection at full resolution would have to reach **into other DataTree nodes** (other levels) and rewrite their indexers. But:

- `IndexSelResult` can only apply indexers to the **same object's** existing variables; it cannot reference another object.
- `DataTree.sel` indexes each node **independently**, with no inter-node communication.

So a "linked index across levels" is **structurally impossible** today — not merely unimplemented. (This corrects the original premise of this page, which assumed cross-level propagation was an index problem.)

## What we do instead

Two mechanisms cover the real need without a cross-node index:

1. **Plain physical `sel`.** Because every level carries its own physical coordinates ([](../mapping/transforms-to-coords.md)), `tree.sel(y=slice(0, 10))` already resolves the *same physical span* correctly at each level — no linking required.
2. **An accessor method** for anything smarter than "same labels per level" — e.g. choosing the coarsest level above a pixel threshold, or returning a single level's crop with its siblings. This is the one place ([](../mapping/multiscales-to-datatree.md)) where cross-level logic legitimately lives.

:::{seealso}
- [](index-overview.md) — why `IndexSelResult` cannot cross objects
- [](../mapping/multiscales-to-datatree.md) — cross-level selection as an accessor concern
- [](../mapping/transforms-to-coords.md) — per-level physical coordinates that make `sel` work
:::
