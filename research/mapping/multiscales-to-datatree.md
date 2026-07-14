# Multiscales → DataTree

An NGFF `multiscales` entry describes a resolution pyramid: a parent group whose child arrays hold the same image at decreasing resolution, related by per-level transforms ([](../spec/multiscales.md)). xarray's `DataTree` is the natural target — a named tree of groups, each wrapping a Dataset — but the fit has sharp edges that this page pins down.

```{admonition} Recommendation
:class: tip
1. One **DataTree node per resolution level**; the multiscale `name` → `DataTree.name` of the root.
2. **Per-level spatial coordinates are local** to each node. Only axes whose length is constant across levels (`c`, `t`) may live on the root and be inherited; `z`/`y`/`x` must **not**.
3. The `multiscales` block (and the rest of `attributes.ome`) lives in the **root node's attrs**, written back to the group's `zarr.json` ([](round-trip.md)).
4. Cross-level selection ("select a region, get every level") is an **accessor method**, not an index — but plain `tree.sel(...)` by physical label already does the right thing.
```

## One node per level

The pyramid's parent group becomes the DataTree root; each entry in `datasets` becomes a child node:

```
/                 (root: name = multiscale name, holds c/t coords + the ome metadata)
├── scale0        (full resolution: local z/y/x coords)
├── scale1        (½: its own, shorter z/y/x coords)
└── scale2        (¼: …)
```

NGFF dataset `path`s are often numeric (`"0"`, `"1"`). A DataTree node name forbids only `/`, so `"0"` is a *legal* node name — mapping it to `scale0` is an ergonomics choice (numeric attribute access is awkward), not a requirement. The multiscale `name` is stored once, as `DataTree.name`, rather than duplicated into attrs.

## Coordinate inheritance fights the pyramid

The placeholder intuition — "inheritance lets shared metadata propagate from parent to children" — is **only half right, and the wrong half is dangerous.** xarray attaches inherited coordinates by aligning child against parent with `join="exact"`. A pyramid's whole point is that `y`/`x` have *different lengths* at each level, so a `y`/`x` coordinate on the root raises a `ValueError` the moment a downsampled child is attached.

The workable rule:

| axis | length across levels | placement |
|---|---|---|
| `c`, `t` | constant | may live on **root**, inherited by all levels |
| `z`, `y`, `x` | shrinks per level | **local to each level node** |

So inheritance is useful for the channel/time coordinates (and their `type`/`unit` attrs), but the spatial coordinates that *define* the pyramid must be local. This is why [](transforms-to-coords.md) materialises a level's spatial coordinates onto that level's node.

## Selection across levels

This is the feature that most wants to be clever and most resists it.

- **Integer `isel` is wrong** across a pyramid: every level has a different pixel count, so `isel(y=10)` means a different physical location at each level.
- **Physical `sel` is right and already works.** `DataTree.sel` broadcasts to all nodes and resolves the *same physical label range* against each node's own coordinates — returning the correct pixels at every resolution (verified: 4 px @ 1 µm, 2 px @ 2 µm for one 0–4 µm span). This is a direct payoff of materialising physical coordinates.
- **It cannot be an index.** One might hope a custom index could link levels so that selecting on full-res narrows the others. The index machinery forbids it: `IndexSelResult` cannot reach another object, and `DataTree.sel` indexes each node independently with no inter-node channel ([](../indexes/index-overview.md)). Any logic beyond "resolve the same labels per level" — e.g. "give me the coarsest level with ≥ 512 px" — must therefore be an **accessor method**, not an index. (The placeholder's link to "linked indexes" for this was a dead end; corrected here.)

## Where the metadata lives, and the DataTree↔Zarr shape

NGFF stores `multiscales` on the **parent group** whose children are the scale arrays. DataTree matches this: each node has its own attrs, attrs are *not* inherited, and node attrs (including nested dicts) round-trip verbatim to `zarr.json`'s `attributes`. So the backend writes `attributes.ome.multiscales` onto the root node's attrs and it lands in the right place.

Two shape mismatches the custom backend must bridge:

- A DataTree **leaf is always a group**, so a level's array lands at `scale0/<var>` rather than as a bare array `scale0`. NGFF expects the dataset `path` to *be* the array. The backend reconciles naming on write.
- `DataTree.to_zarr(group=...)` currently raises `NotImplementedError`, and Zarr v3 consolidated metadata warns. The custom backend writes the group structure directly rather than relying on these.

## Rejected alternatives

- **A flat Dataset with one variable per level** (`scale0`, `scale1`, … as separate data variables in a single Dataset, sharing nothing). Rejected: levels have different `y`/`x` lengths, so they cannot share dimensions; you end up with `y0`/`y1`/… proliferation and lose the natural "same image, different resolution" grouping that DataTree expresses.
- **Level-switching on a single object** (`bioio`'s `set_resolution_level()`). Rejected: there is no unified multi-resolution object, so you cannot hold or select across the whole pyramid at once — exactly what DataTree gives us.

## Open question

A single group **may** legally contain more than one `multiscales` entry (e.g. an image plus a derived one). One DataTree root is one image, so this maps to either multiple roots or a convention this RFC leaves open (see [The Proposal § Open questions](../summary.md)); rare in practice.

:::{seealso}
- [](../spec/multiscales.md) — the `datasets`/`version`/`name` structure
- [](../xarray/datatree.md) — DataTree, coordinate inheritance, node attrs
- [](transforms-to-coords.md) — why per-level spatial coordinates are local
- [](round-trip.md) — writing `attributes.ome.multiscales` back onto the group
:::
