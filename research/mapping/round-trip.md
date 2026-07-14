# Round Trip

The whole mapping is judged by one test: read an OME-Zarr, manipulate it, write it back, and lose nothing the user did not intend to change — including fields no version of our library understands. This page specifies the mechanism that delivers that: a **custom backend** plus a **raw-`zarr.json` carrier**.

```{admonition} Recommendation
:class: tip
1. Read and write through a **custom backend** (`engine="ome-zarr"`), so the library controls both directions and is not constrained by what `to_zarr()` happens to serialise.
2. On read, keep the raw `attributes.ome` block as an **opaque carrier**. Derive the working representation (dims, coords, DataTree) from it, but preserve the carrier itself.
3. On write, **regenerate the managed fields** from xarray state and **deep-merge them over the carrier** — never let the typed engine emit a fresh metadata block.
4. "Never lose data" = the on-disk `attributes.ome` (and sibling namespaces) survives read→write byte-for-byte except where the user changed mapped state.
```

## Why a custom backend, not `to_zarr()`

The standard `Dataset.to_zarr()` path can only persist what xarray serialises natively — variable data, attrs, and a whitelist of encoding keys. That is too narrow for NGFF:

- it cannot cleanly write a group-level `ome` namespace shaped the way the spec requires;
- `DataTree.to_zarr(group=...)` raises `NotImplementedError` and Zarr v3 consolidated metadata warns ([](multiscales-to-datatree.md));
- it offers no hook to reconstruct transform parameters, level structure, or preserved unknown fields.

A custom backend owns read *and* write, which is what lets the in-memory representation be ergonomic (plain coordinates, a DataTree, a typed accessor) while the on-disk form stays exactly conformant. This decoupling is the single most important architectural choice in the mapping.

## The carrier

The typed engine we build on (`ngff-zarr`) is **lossy on its own**: it silently drops unknown keys inside `attributes.ome`, drops extra omero/transform/`metadata` fields, mutates recognised fields on write, and *raises* on an unexpected key inside an axis object (verified empirically — see `notes/field-research/ngff-zarr-roundtrip-verification.md`). It is an excellent typed *view* and array I/O engine, but it cannot be the round-trip authority.

So the backend reads the raw `zarr.json` itself and partitions `attributes.ome` into two parts:

- **Managed fields** — the ones the mapping actively represents in xarray: axis names/`type`/`unit`, the multiscale structure and per-level transforms, omero channel labels. These are *regenerated* from xarray state on write.
- **Unmanaged remainder** — everything else: unknown `ome` keys, vendor extensions, the full omero `color`/`window`, extra `metadata`, future transform types. These are kept **verbatim**.

On write, the backend produces the managed fields from the live xarray objects and **deep-merges** them onto the preserved carrier, then writes the result — rather than calling the typed engine's writer, which would assign a fresh `ome` block and discard the remainder.

```
read:   zarr.json.attributes.ome ─┬─→ managed → dims / coords / DataTree / labels  (working view)
                                  └─→ carrier (kept whole, opaque)
write:  xarray state → managed fields ──┐
                                        ├─ deep-merge ─→ attributes.ome → zarr.json
        carrier (unmanaged remainder) ──┘
```

### Where the carrier lives in memory

Because the user holds a *plain xarray object* (the accessor model, [](axes-to-dims.md)), the carrier has to travel with that object to survive manipulation — it cannot live only in the backend. We store it under a single reserved key in the **root node's attrs** (e.g. `attrs["_ome"]`). This is a deliberate, bounded exception to the "no raw dicts in attrs" rule from [](axes-to-dims.md): the carrier is *opaque round-trip state*, never the working representation, and it is one well-known key rather than scattered metadata. The cost is that it is faintly visible in the repr; the benefit is that round-trip fidelity survives any sequence of xarray operations, not just an unbroken backend session. attrs (including nested dicts) round-trip losslessly through Zarr v3, so the carrier itself persists cleanly.

## What "never lose data" means, concretely

The contract is testable: for any conformant store, `open → write` (with no user edits) must produce an `attributes.ome` that is **deep-equal** to the original (modulo key ordering). With edits, only the mapped fields the user touched may differ. This is stronger than the current reference implementation guarantees, and stronger than any surveyed library provides — `ome-zarr-py` preserves unknown fields only because it keeps everything as untyped dicts; we get the same fidelity *and* a typed working view.

```{warning}
The `xarray_ngff` reference implementation realises this design: the backend keeps the raw `attributes.ome` block as a carrier and re-merges it on write via `_merge_carrier_into_store` (managed `multiscales` regenerated from xarray state win; every other key is preserved). The round-trip guarantee is **property-tested** — an unknown carrier field and the verbatim `omero` block are checked to survive `open → write → open` across a broad stream of generated stores.
```

## Rejected alternative

- **`to_zarr()` plus post-processing.** Write with the standard path, then patch `zarr.json` to inject the `ome` namespace. Rejected: it is fragile (two writers fighting over the same metadata), still cannot express the DataTree group shape NGFF wants, and provides no clean place for the carrier. The custom backend subsumes it.

:::{seealso}
- [](../spec/axes-experiments.ipynb) — Experiment 8 first framed the round-trip constraints
- [](axes-to-dims.md) — the carrier as the bounded exception to "no raw dicts in attrs"
- [](transforms-to-coords.md) — why transforms are written from the carrier, not re-derived
- [](omero-to-coords.md) — color/window/unknown omero fields preserved via the carrier
- [](../xarray/encoding.md) — why `encoding` cannot serve as the carrier
:::
