# The Proposal: NGFF 0.5 → xarray

This is the heart of the RFC: how NGFF 0.5 (OME-Zarr) metadata maps into xarray's data model such that the result is *robust to user mistakes*, *usable for developers*, and *never loses data*. It collects the per-field recommendations (detailed in [The Mapping](mapping/axes-to-dims.md)) into a single proposal. The [introduction](intro.md) covers motivation, goals, and scope.

## Scope

In scope: single-image multiscale data — `axes`, `coordinateTransformations`, `multiscales`, and `omero` channel metadata, on NGFF 0.5 / Zarr v3. Out of scope for the initial RFC: high-content-screening plate/well metadata and labels/segmentation.

## The recommended mapping

| NGFF field | xarray home | notes |
|---|---|---|
| axis `name` | **dimension name**, verbatim | no case-folding, no canonical reorder ([](mapping/axes-to-dims.md)) |
| axis order | **dimension order**, preserved | canonical `TCZYX` offered only as a *view* |
| axis `type`, `unit` | **coordinate `attrs`** (`axis_type`, `units`) | read via the `.ngff` accessor; `units` chosen for cf/pint interop |
| `coordinateTransformations` | **lazy physical coordinates** — a `TransformIndex` storing `(scale, translation)`, computing `t + s·arange(N)` on access | a derived read-view with world-unit `.sel`; originals preserved in the carrier ([](mapping/transforms-to-coords.md)) |
| `multiscales` (pyramid) | **DataTree**, one node per level | spatial coords *local* per level; `c`/`t` may be inherited ([](mapping/multiscales-to-datatree.md)) |
| `multiscales.name` | **`DataTree.name`** | stored once, not duplicated in attrs |
| omero channel `label` | **`c` dimension coordinate** (strings) | enables `sel(c="DAPI")` ([](mapping/omero-to-coords.md)) |
| omero `color`, `window`, rest | **carrier**, surfaced read-only via accessor | rendering hints, not selection keys |
| unknown / future fields | **raw-`zarr.json` carrier** | preserved verbatim, re-merged on write ([](mapping/round-trip.md)) |

## The layered architecture

The API is deliberately layered so each concern has exactly one home:

- **Public API** — a `.ngff` accessor on `Dataset`/`DataTree`: reads typed metadata, builds objects, and performs cross-level multiscale selection. It is the *front door*, not the storage, validator, or selector. (Chosen over subclassing — which loses its type through operations — and over a wrapper object — which gives up being "just xarray". This is the rio/cf/pint pattern.)
- **Persistence** — native xarray structures (dimension names, coordinate attrs, `DataTree.name`) plus the raw-`zarr.json` carrier for everything unmodelled.
- **Validation** — a typed model (the `ngff-zarr` view) used *inside* the accessor and backend to make malformed metadata hard to construct.
- **Selection** — a parameter-backed lazy `TransformIndex` (a `CoordinateTransformIndex` subclass) that adds world-unit scalar/slice/bbox `.sel`; a plain dense coordinate is an equivalent fallback ([](mapping/custom-index-design.md)).

## The round-trip contract

A **custom backend** (`engine="ome-zarr"`) owns both read and write, decoupling the ergonomic in-memory form from the conformant on-disk form. Because `ngff-zarr` alone is lossy (it drops unknown fields and can raise on unexpected axis keys), the backend keeps the raw `attributes.ome` block as a carrier, regenerates the *managed* fields from xarray state on write, and **deep-merges** them over the carrier. The testable guarantee: `open → write` with no edits reproduces `attributes.ome` byte-for-byte (modulo key order); with edits, only touched fields change.

## Reference implementation

This proposal is not just a design — it is implemented and verified. The `xarray_ngff` package provides `open_ngff_dataset`/`open_ngff_datatree`, `write_ngff_dataset`/`write_ngff_datatree`, an `engine="ome-zarr"` backend (with an `"ngff"` alias), and the `.ngff` accessor, built exactly as described above: axis `type`/`unit` on coordinate attrs, transforms surfaced as lazy `TransformIndex`-backed coordinates (`indexes/`) with world-unit `.sel`, a multiscale `DataTree`, and the raw-`zarr.json` carrier with the deep-merge write path.

Crucially, the design's core guarantees are **property-tested**, not just asserted. A suite drives the package with a broad, schema-valid stream of generated OME-Zarr documents (via the sibling `ome-zarr-hypothesis` generator) and checks that, across that space:

- `.sel` on any physical coordinate always resolves (scalar and inclusive slice);
- a unit is surfaced **iff** the store declared one (never fabricated);
- an unknown carrier field and the verbatim `omero` block survive a write round-trip (Dataset and DataTree);
- `open → write → open` reproduces axis names and physical coordinates at every pyramid level.

In short, the proposal below is a description of working code, not an aspiration.

## Open questions for the community

1. **Axis `type`/`unit` keys** — `axis_type`/`units` on coordinate attrs is the recommendation; the exact key names and their relationship to a future typed spec are worth community input.
2. **Multiple `multiscales` per group** — rare but legal; one DataTree root is one image, so the convention for multi-image groups is unfixed ([](mapping/multiscales-to-datatree.md)).
3. **Carrier visibility** — the carrier lives under a reserved root-attrs key so it survives manipulation; this is a small repr cost for full fidelity, and alternatives (e.g. backend-held state) trade fidelity for cleanliness.
4. **RFC-5 affine transforms** — the carrier preserves them now. The index machinery already handles N-D affine (and even non-affine invertible) transforms, so surfacing them as coordinates awaits a settled RFC-5 spec and `ngff-zarr` read support, not new index work.

:::{seealso}
- [](mapping/axes-to-dims.md), [](mapping/transforms-to-coords.md), [](mapping/multiscales-to-datatree.md), [](mapping/omero-to-coords.md) — the per-field decisions
- [](mapping/round-trip.md) — the carrier and write contract
- [](prior-art.md) — the six libraries this proposal learns from
:::
