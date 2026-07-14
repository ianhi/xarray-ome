# xarray-ngff RFC: An xarray representation for OME-Zarr (NGFF 0.5)

This document is the **xarray-ngff RFC**. It proposes how [NGFF 0.5](spec/ngff-0.5-spec.md) (OME-Zarr) metadata should map into [xarray](https://docs.xarray.dev)'s data model — dims, coordinates, attributes, indexes, and `DataTree` — and defines the read/write contract a library must uphold to make that mapping faithful.

```{note}
This is an **xarray-ngff project RFC**, not an OME/NGFF-process RFC. It specifies an in-memory representation and I/O contract for one library. Where it touches live NGFF work — RFC-3 (axis constraints) and RFC-5 (coordinate systems/transforms) — that is flagged as forward-looking, not as a position on the spec itself.
```

## Abstract

OME-Zarr stores a small, well-defined set of image metadata (axes, coordinate transformations, a multiscale pyramid, and omero channel descriptors) as JSON in `zarr.json`. xarray has a mature, widely-understood model for labelled N-D arrays. This RFC maps one onto the other so that an OME-Zarr image opens as an ordinary xarray `Dataset`/`DataTree` — selectable in physical coordinates, discoverable through a typed accessor — and writes back **without losing anything**, including fields the library does not model. The proposal is realised by a working, property-tested reference implementation (`xarray_ngff`).

## Motivation and goals

Reading OME-Zarr into xarray is easy to do badly: dump the JSON into `attrs` as raw dicts, materialise coordinates, and write back a lossy approximation. Doing it *well* — so the result is safe to manipulate, pleasant to program against, and byte-faithful on round-trip — requires deliberate choices about where each piece of metadata lives. This RFC is those choices. It is guided by three requirements, in priority order:

1. **Robust to user mistakes** — no raw dicts in `attrs` that a user can silently corrupt; the API makes wrong states hard to construct.
2. **Usable for developers** — typed, structured, discoverable; an OME-Zarr image is *just an xarray object* the rest of the ecosystem already understands.
3. **Never loses data** — full round-trip fidelity, including unknown and future fields (forward compatibility).

## Scope

**In scope:** single-image multiscale data on NGFF 0.5 / Zarr v3 — `axes`, `coordinateTransformations`, `multiscales`, and `omero` channel metadata.

**Out of scope (initial RFC):** high-content-screening `plate`/`well` metadata and labels/segmentation. These are deferred, not precluded; the round-trip carrier already preserves them verbatim.

## How to read this RFC

- **[The Proposal](summary.md)** — the recommended mapping, the layered architecture, and the round-trip contract, in one page. Start here.
- **The Mapping (detailed decisions)** — one page per field (`axes`, transforms, `multiscales`, `omero`, round-trip, custom index), each in *recommendation + rejected-alternatives* form. This is the normative detail behind the proposal.
- **Appendices** — background and rationale: the NGFF 0.5 spec as it pertains to this mapping, the relevant parts of xarray's data model, the custom-index design space, and a survey of prior art the proposal learns from.

Audience: developers building or reviewing the xarray-ngff library, and community reviewers evaluating the approach.
