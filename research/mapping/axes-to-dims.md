# Axes → Dims

The `axes` array is where the NGFF↔xarray mapping is most natural: an NGFF axis and an xarray dimension are the same concept — a named, ordered grid direction. This page proposes how each part of an axis (`name`, `type`, `unit`) maps, and records the alternatives we rejected.

```{admonition} Recommendation
:class: tip
1. **`name` → dimension name, verbatim.** Each entry in `axes` becomes one xarray dimension; the axis `name` is used unchanged (no case-folding, no canonical letters).
2. **Axis order → dimension order, preserved.** The order of the `axes` array is the dimension order. We do not impose a canonical `TCZYX` layout; a canonical *view* can be offered as a convenience, but it is not the stored model.
3. **`type` and `unit` → attributes on the axis's coordinate variable**, surfaced through a typed `.ngff` accessor — never as a raw dict in `Dataset`/`DataArray` `attrs`, and never in `encoding`.
4. **Unknown axis fields → preserved verbatim** by the raw-`zarr.json` round-trip carrier (see [](round-trip.md)), not by the typed model.
```

## `name` → dimension name

NGFF axis names are free-form strings. In practice they are short (`t`, `c`, `z`, `y`, `x`), but the spec does not restrict them, and forthcoming work (NGFF RFC-3) loosens axis constraints further. The mapping is therefore: **use the name as the dimension name, unchanged.**

```python
# axes: [{"name": "t", ...}, {"name": "c", ...}, {"name": "z", ...},
#        {"name": "y", ...}, {"name": "x", ...}]
da.dims          # ('t', 'c', 'z', 'y', 'x')
```

This is the *unambiguous* part of the mapping: dimension names are exactly what xarray uses to align, select, and broadcast, and NGFF axis names already play that role on disk (NGFF 0.5 even requires array-level `dimension_names`, see [](../spec/zarr-v3.md)).

### Why verbatim, and not a canonical order

A major incumbent, `bioio`/`aicsimageio`, forces every image into a fixed 5-D `TCZYX` order with **uppercased single-letter** dimension names (see [](../prior-art.md)). That is excellent for interop — downstream code always knows where `Z` is — but it is **lossy against NGFF**: a store with axes named `["time", "channel", "λ", "y", "x"]` cannot survive the trip, and the original order is discarded. Because our first requirement is *never lose data*, the stored model must preserve names and order exactly. A `TCZYX`-style canonical reordering is genuinely useful and can be exposed as a method on the accessor (a *view*), but it is a convenience layered on top of the faithful representation, not the representation itself.

## `type` and `unit` → coordinate attributes + a typed accessor

Each axis carries up to two semantic fields beyond its name:

| field | example | meaning |
|---|---|---|
| `type` | `"space"`, `"time"`, `"channel"`, or custom | the kind of axis |
| `unit` | `"micrometer"`, `"second"` | physical unit (UDUNITS-style) |

These do not map to a *dimension* (a dimension is just a name and a length). They are metadata *about* the axis, and the question — the one the axes research spent most of its effort on — is **where in xarray's data model they should live.**

We recommend storing them as **attributes on the axis's coordinate variable**, using the conventional CF/pint key `units` for the unit and `axis_type` for the type, and reading them back through a typed accessor rather than by reaching into `attrs` directly.

```python
ds["x"].attrs            # {'units': 'micrometer', 'axis_type': 'space'}
ds.ngff.axes["x"].type    # 'space'   (typed, validated, discoverable)
ds.ngff.axes["x"].unit    # 'micrometer'
```

Every axis already gets a coordinate variable in our mapping — the physical coordinate materialised from its `coordinateTransformations` (see [](transforms-to-coords.md)), or, for a channel axis, the string channel labels (see [](omero-to-coords.md)). So there is always a coordinate to hang `type`/`unit` on; we are not inventing a place for them.

### Why a *coordinate's* attrs, not the `Dataset`'s

This choice is driven by what xarray operations actually preserve. Two clarifications matter, because the folklore here is misleading:

- **Attrs are more durable than "attrs are fragile" suggests.** Modern xarray keeps `attrs` through reductions (`.mean()`), elementwise ops, and slicing by default, and `attrs` — including nested dicts — round-trip losslessly through the Zarr v3 backend. The genuine loss vectors are narrow: binary ops between objects with *conflicting* values, `merge`/`concat` (which default to keeping only the first object's attrs), and explicit `keep_attrs=False`.
- **Putting axis metadata on the *coordinate* avoids the worst of those vectors.** A coordinate's `units`/`axis_type` ride with that coordinate through selection and alignment; they are not entangled with the data variable's attrs and are not at the mercy of `Dataset`-level merges in the same way. This is exactly the pattern `rioxarray` uses for CRS (stored on a coordinate, not in data-variable attrs) precisely because data-variable attrs are the easiest to drop.

Using the conventional key `units` (rather than an `ome_unit`) is deliberate: it gives free interoperability with `cf-xarray` and `pint-xarray`, which already read `units` from coordinate attrs. We rename only `type` → `axis_type`, to avoid colliding with Python's `type` and with any future xarray attribute conventions.

### Why a typed accessor on top — and what it is *not*

Raw attrs satisfy *durability* but not requirement #2 (*usable for developers*): a user should not have to know that the unit lives under `ds["x"].attrs["units"]`. A typed `.ngff` accessor gives a discoverable, validated read API (`ds.ngff.axes["x"].unit`) and is the single place that knows the storage convention. We choose an accessor over the alternatives (subclassing `Dataset`, or a `bioio`-style wrapper object) because it keeps an OME-Zarr image *a plain xarray object* — one the rest of the ecosystem already understands — which subclassing cannot (xarray operations return base-class instances) and a wrapper deliberately gives up. This is the same choice `rioxarray` (`.rio`), `cf-xarray` (`.cf`), and `pint-xarray` (`.pint`) made, and the one xarray's own extension guidance recommends.

It is worth being precise about the accessor's role, because it is a *front door*, not the whole API. The library is layered:

| layer | responsibility | for axes |
|---|---|---|
| **public API** — `.ngff` accessor | read/interpret metadata; build; cross-level selection | `ds.ngff.axes["x"].unit` |
| **persistence** — native xarray + raw carrier | where bytes actually live | coord attrs `units`/`axis_type`; unknown fields in the carrier |
| **validation** — typed model | make wrong things hard | the `ngff-zarr` typed view, used *inside* the accessor and backend |
| **selection** — coords + custom index | label-based indexing | the axis coordinate itself (see [](transforms-to-coords.md)) |

So the accessor *reads* `type`/`unit`; it does not store them (the coordinate's attrs do), validate them (the typed model does), or perform `.sel()` (xarray's indexing on the coordinate does). Keeping these separate is what lets the representation stay faithful while the API stays ergonomic.

## Rejected alternatives

```{admonition} Alternative A (chosen) vs. the rest
:class: note
The axes notebook ([](../spec/axes.ipynb)) explores eight experiments. The two finalists were **CF-style coordinate attrs** (chosen) and a **separate `axis` dimension**. The others are recorded here as rejected.
```

- **A separate `axis` dimension** (a 2-D table of axis metadata indexed by an `axis` coordinate). *Visible in the repr and queryable with plain xarray*, which is attractive. Rejected because it is a novel pattern with no ecosystem precedent, it is orthogonal-but-awkward (the metadata sits in a side table disconnected from the dimensions it describes), and it trips the `None → nan` object-array gotcha for absent units. The CF pattern is 20+ years proven and gives pint/cf interop for free.
- **A raw NGFF dict in `Dataset.attrs`** (e.g. `attrs["ome"]["multiscales"][0]["axes"]`). Rejected by requirement #1: it is an untyped dict that users can corrupt, it does not track renames or reordering of dimensions, and it duplicates state that should be derived. (We *do* keep the raw NGFF blob — but as an opaque round-trip carrier, not as the working representation; see [](round-trip.md).)
- **The `encoding` dict.** Rejected outright: the Zarr backend whitelists only codec/layout keys and **silently deletes** anything else on write. `encoding` is for storage mechanics, not domain metadata (see [](../xarray/encoding.md)).
- **Fixed `TCZYX`, uppercased names** (the `bioio` model). Rejected for the stored representation because it discards original names and order (lossy). Retained only as an optional convenience *view*.

## Forward compatibility

The typed model deliberately understands only the fields it maps (`name`, `type`, `unit`). Anything else on an axis object — a custom key, a field from a future spec version — is **not** dropped: it is carried verbatim in the raw-`zarr.json` round-trip carrier and re-merged on write. This matters because the typed engine we build on (`ngff-zarr`) *raises* on an unexpected key inside an axis object, so the round-trip carrier (not the typed model) is what makes unknown axis fields survive. See [](round-trip.md) for the mechanism.

:::{seealso}
- [](../spec/axes.ipynb) — the eight experiments and the two-alternative analysis behind this decision
- [](transforms-to-coords.md) — where each axis's coordinate (the home for `type`/`unit`) comes from
- [](omero-to-coords.md) — the channel axis, whose coordinate is string labels rather than physical coords
- [](round-trip.md) — the raw-`zarr.json` carrier that preserves unknown axis fields
- [](../xarray/data-model.md) — what xarray operations preserve vs. drop for attrs
:::
