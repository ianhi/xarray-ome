# Omero → Coords

`omero` carries channel rendering metadata: per-channel `label`, `color`, and a `window` (display min/max) ([](../spec/omero.md)). Only one piece of it is a natural xarray coordinate; the rest is rendering state that we preserve but do not promote.

```{admonition} Recommendation
:class: tip
1. Channel **`label` → the `c` dimension coordinate** (a 1-D string coordinate), enabling `da.sel(c="DAPI")`.
2. **`color`, `window`, and every other omero field → preserved in the round-trip carrier** ([](round-trip.md)) and surfaced through the accessor (`ds.ngff.channels["DAPI"].color`) — *not* stored as coordinate attrs or extra coordinates.
3. Treat omero as **data to preserve, not a stable contract**: it is officially transitional in the spec (a successor is in progress), so the mapping must round-trip it faithfully without depending on its shape.
```

## Labels → the channel coordinate

Channel labels are the one omero field that is genuinely *coordinate-like*: one value per position along `c`, used to identify and select. They become the `c` dimension coordinate:

```python
da["c"].values          # array(['DAPI', 'GFP', 'mCherry'], dtype=object)
da.sel(c="DAPI")        # selects the channel by name
```

It must be the **dimension coordinate** on `c`, not a non-dimension coordinate. This is a real xarray gotcha: `.sel()` on a *non-indexed* coordinate is a silent no-op — it returns the full array with no error. Label selection works only because the channel labels index the `c` dimension. (The `c` axis's `type`/`unit` attrs still live on this coordinate, per [](axes-to-dims.md); for `c` there is no physical `unit`.)

## Color, window, and the rest stay out of the coordinate space

`color` (an RGB hex string) and `window` (`min`/`max`/`start`/`end` floats) are **rendering hints**, not selection keys. They do not belong in xarray's coordinate space:

- They are not things you `.sel()` on, so making them coordinates buys nothing.
- Spreading them across coordinate attrs makes them fragile under operations and clutters the repr.
- `bioio` simply **drops** them; we will not — but we keep them where they cannot decohere: the carrier, surfaced read-only through the typed accessor.

So the division mirrors the rest of the design: the *selectable* part (labels) becomes a real coordinate; the *descriptive* part (color/window/unknown fields) rides in the carrier and is read through `.ngff`.

## Edge cases

- **No labels.** `label` is optional. With no labels, `c` has no string coordinate and falls back to an integer dimension; selection is positional. The accessor should report channels by index in that case.
- **Duplicate labels.** Nothing in the spec forbids two channels sharing a label; `da.sel(c="DAPI")` would then return multiple positions. We preserve them as-is (faithful) and let xarray's normal duplicate-label behaviour apply rather than silently renaming.
- **Channel count vs. `c` length.** The omero channel list should match the `c` dimension length; a mismatch is a malformed store. We preserve what is on disk and surface the discrepancy through the accessor rather than papering over it.

## Forward compatibility

Because omero is transitional, the carrier preserves the **entire omero block** verbatim — including fields we do not model and a future successor namespace — so that a manipulate-and-write cycle never degrades it. The labels-as-coordinate mapping is purely a read-time convenience derived from that preserved block.

:::{seealso}
- [](../spec/omero.md) — the channel/`window`/`color` schema and its transitional status
- [](axes-to-dims.md) — the `c` axis and where its `type`/`unit` live
- [](transforms-to-coords.md) — why the channel coordinate is labels, not `scale[c]`
- [](round-trip.md) — the carrier that preserves color/window/unknown omero fields
:::
