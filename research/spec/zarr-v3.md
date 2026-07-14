# Zarr v3

NGFF 0.5 mandates Zarr v3. Two Zarr v3 features matter directly for the xarray mapping: the consolidated `zarr.json` file (replacing v2's `.zarray` / `.zgroup` / `.zattrs` split), and the first-class **`dimension_names`** field. The rest of the v3 changes (codecs, chunk grids, data types) are plumbing that xarray-ngff inherits from zarr-python.

## `zarr.json`: one file per node

Every Zarr v3 node — every group and every array — has a single `zarr.json` file. Its shape depends on `node_type`:

**Group**

```json
{
  "zarr_format": 3,
  "node_type": "group",
  "attributes": {
    "ome": {
      "version": "0.5",
      "multiscales": [ ... ],
      "omero": { ... }
    }
  }
}
```

**Array**

```json
{
  "zarr_format": 3,
  "node_type": "array",
  "shape": [1, 2, 10, 256, 256],
  "data_type": "uint16",
  "chunk_grid": { "name": "regular", "configuration": { "chunk_shape": [1, 1, 1, 256, 256] } },
  "chunk_key_encoding": { "name": "default" },
  "fill_value": 0,
  "codecs": [ ... ],
  "dimension_names": ["t", "c", "z", "y", "x"],
  "attributes": {}
}
```

## The `ome` namespace

OME-Zarr metadata lives under `attributes.ome` in the *group* `zarr.json`. The `ome` key is a namespace, not a mixin — sibling keys under `attributes` belong to other extensions and MUST be preserved unchanged. The `version` string inside the namespace identifies the NGFF version:

```json
"attributes": {
  "ome": { "version": "0.5", "multiscales": [...] }
}
```

The spec requires consistency: *every* node in an OME-Zarr hierarchy that carries `ome` metadata MUST declare the same version. Mixed-version hierarchies are illegal.

## `dimension_names`: first-class in v3

The single most load-bearing change for the xarray mapping. Zarr v3 arrays carry `dimension_names` in their `zarr.json`, independent of any extension. The NGFF 0.5 spec requires this field to be present on every array in a multiscale group, and requires it to match the `axes` names in the group-level `multiscales` metadata:

> The `"dimension_names"` attribute MUST be included in the `zarr.json` of the Zarr array of a multiscale level and MUST match the names in the "axes" metadata.

Practical consequences:

1. **Dim names are available without parsing NGFF.** `zarr.open_array(...).metadata.dimension_names` is enough to produce xarray dims, even if the consumer knows nothing about OME-Zarr. xarray's Zarr backend already uses this path.
2. **NGFF axis names are duplicated across files.** The group-level `multiscales[].axes[].name` and every child array's `dimension_names` must agree. Our writer must keep them in sync; our reader can treat them as redundant (and warn on mismatch).
3. **xarray-native stores "just work" for dims.** If you write a plain xarray Dataset to a Zarr v3 store, dim names land in `dimension_names` automatically. Adding OME metadata is a layer on top; it does not overwrite the dim names.

## Why v3 matters for the mapping

Three reasons, in order of importance:

1. **`dimension_names` eliminates ambiguity.** In v2, xarray's Zarr backend used a `_ARRAY_DIMENSIONS` attribute convention that NGFF did not guarantee. In v3 the dim names are standardized and NGFF aligns with them.
2. **Namespaced attributes cleanly separate xarray-land and NGFF-land.** An xarray-ngff writer can put encoding-level details under one key, NGFF metadata under `ome`, and they do not collide.
3. **The mapping is easier to specify.** We can say "read `dimension_names` for dims, read `ome.multiscales[].axes[].type` and `.unit` for type/unit" and have each claim resolve to exactly one location in the store.

## Compatibility implications

- **Zarr v2 stores are out of scope.** `pydantic-ome-ngff` is v2-only and therefore incompatible; this is already noted in the project CLAUDE.md.
- **`ome-zarr-py` readers that predate v3 do not apply.** The reference reader has a v3 branch; writers and readers we build on must be v3-aware.
- **zarr-python 3.x is the floor.** The research notebooks already pin it in `research/pyproject.toml`.

## Edge cases worth naming

- **Missing `dimension_names`.** Spec-illegal in a multiscale array. Reader policy: synthesize from `axes`, warn.
- **Mismatched `dimension_names` and `axes[].name`.** Again, spec-illegal. Treat `axes[].name` as authoritative (it carries the type/unit too) and warn.
- **Hidden keys under `attributes`.** Non-`ome` sibling keys belong to other extensions (or user content). Must pass through unread, unmodified.
- **Empty `ome` namespace.** A Zarr v3 group with an `ome` key but no `multiscales` is spec-legal but not an image. Handle gracefully.

## What this page is *not*

This page intentionally does not cover:

- Codec selection and chunking decisions (delegated to zarr-python; no NGFF-specific logic).
- Consolidated metadata (`zarr.json` at the root aggregating descendants) — relevant for performance, not for the mapping.
- The Zarr v3 data type system — inherited through zarr-python.

:::{seealso}
- [](ngff-0.5-spec.md) — the full specification
- [](axes.ipynb) — uses `dimension_names` and `MemoryStore` from Zarr v3
- [](multiscales.md) — the `ome` namespace payload this page describes plumbing for
:::
