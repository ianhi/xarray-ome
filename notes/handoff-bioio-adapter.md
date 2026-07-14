# Handoff: a `bioio → xarray-ngff` adapter

**Branch:** `metadata-conversion-refactor` (a *new, distinct workstream*; the
package + RFC work is committed — see `notes/handoff-xarray-ngff-package.md` and
`notes/handoff-property-tests.md`).
**Status:** not started. This doc scopes it.

## Goal

Provide an adapter that takes an image loaded by [`bioio`](https://github.com/bioio-devs/bioio)
and returns it in **our** representation — the `xarray_ngff` layer: real axis
dims, physical coordinates with units, omero channel labels, and the verbatim
`ome` carrier surfaced through the `.ngff` accessor. In one sentence: *bioio
fetches the bytes; we re-impose the OME-Zarr metadata bioio flattened away.*

Proposed entry point: `xarray_ngff.adapters.bioio.from_bioio(img) -> xr.Dataset | xr.DataTree`
(accepting a `bioio.BioImage` or its `.xarray_dask_data`).

## Why this exists (the motivating contrast — already in the RFC)

bioio normalises every format to a fixed `TCZYX` shape, so it cannot honour what
an OME-Zarr store declares. On IDR `idr0066`
(`https://livingobjects.ebi.ac.uk/idr/zarr/v0.5/idr0066/ExpD_chicken_embryo_MIP.ome.zarr`,
**note: no trailing slash**), a 2-D `(y, x)` micrometer-calibrated image with an
omero channel `"Cy3"`:

- **bioio** → dims `(T:1, C:1, Z:1, Y:8978, X:6510)` (three invented size-1 axes),
  `Y`/`X` with **no coordinates** (1.6 µm scale + `micrometer` unit dropped), the
  channel coord fabricated as `'Channel:/:0'`, and the raw block parked in
  `attrs['unprocessed']` as an opaque `GroupMetadata` object.
- **`xarray_ngff.open_ngff_dataset`** → dims `(y, x)`, `y`/`x` = `0, 1.6, 3.2 …`
  µm (`TransformIndex`-backed) with `units='micrometer'`, `.ngff.channels ==
  ['Cy3']`, full `ome` carrier.

This worked example lives in `research/prior-art.md` (§ bioio → "Seen
concretely"). The adapter is the constructive follow-up: turn a bioio object into
the right-hand column.

## The key seam (non-obvious, saves you the discovery)

bioio **preserves the raw OME-Zarr group metadata** on the xarray object:

```python
img.xarray_dask_data.attrs['unprocessed']            # a bioio GroupMetadata
img.xarray_dask_data.attrs['unprocessed'].attributes['ome']   # the full ome dict
```

That dict is exactly what our reader already consumes. So for an OME-Zarr source
the highest-fidelity adapter does **not** try to un-mangle bioio's TCZYX
DataArray — it recovers the pristine `ome` block from `unprocessed` and rebuilds
our representation from it, reusing the tested machinery in `xarray_ngff`:
`reader` (axes→dims, `transform_coords`→coords, omero→channel, carrier at
`attrs['ome']`) and `indexes.transform_coords` / `TransformIndex`. Feed it the
`ome` block + the dask arrays; do not re-derive scale from bioio's coordinate
values.

## Suggested design — two tiers

1. **OME-Zarr source (high fidelity).** If `attrs['unprocessed']` carries an `ome`
   block, reconstruct our Dataset/DataTree from it (reuse the reader path). The
   acceptance bar is *equality with `open_ngff_dataset(url)`* (see Verify).
2. **Non-OME-Zarr source (normalise the mess).** For CZI/ND2/LIF/etc. there is no
   `ome` block — only bioio's flattened surface. Synthesize our layer from it:
   - drop invented size-1 axes not backed by real metadata (careful: keep
     genuinely size-1 axes); map remaining dims to axis names;
   - `img.physical_pixel_sizes` (Z/Y/X) → per-axis `scale` → `transform_coords`
     (units are implicit in bioio; default to `micrometer`? — **decision needed**);
   - `img.channel_names` → `c` coordinate + a minimal synthesized `omero` carrier;
   - stash anything unmapped (e.g. `img.metadata`) in the carrier so nothing is lost.

   Start with tier 1; tier 2 is a bigger, lossier surface — land it behind the
   same `from_bioio` entry point once tier 1 is solid.

## Open decisions (raise with the user)

- **Package placement + deps.** `xarray_ngff/adapters/bioio.py`; add `bioio` +
  `bioio-ome-zarr` as an **optional/extra** (not a core dep — the core must not
  pull bioio). Mirror the ozh dev-only pattern.
- **Multiscale.** bioio surfaces a single resolution (`.set_resolution_level`);
  decide whether `from_bioio` returns a `DataTree` (all levels, recovered from the
  `ome` block) or just the finest `Dataset`.
- **Tier-2 unit default.** bioio drops units; do we assume `micrometer` or leave
  coords uncalibrated (`.ngff.calibrated == False`, honouring rule 4 — never
  fabricate units)? Rule 4 argues for **uncalibrated** unless bioio exposes a unit.
- **omero-without-channel-axis edge case.** This IDR store declares omero channels
  but has **no `c` axis** (2-D). `open_ngff_dataset` handled it (channels surfaced,
  no `c` dim); make sure the adapter matches that behaviour.

## Verify (acceptance)

```bash
cd /Users/ian/Documents/dev/xarray-ome
uv run --with bioio --with bioio-ome-zarr python -c "
from bioio import BioImage
import xarray_ngff
from xarray_ngff.adapters.bioio import from_bioio   # to build
url='https://livingobjects.ebi.ac.uk/idr/zarr/v0.5/idr0066/ExpD_chicken_embryo_MIP.ome.zarr'
got = from_bioio(BioImage(url))
ref = xarray_ngff.open_ngff_dataset(url)
assert dict(got.sizes) == dict(ref.sizes), (got.sizes, ref.sizes)     # {'y':8978,'x':6510}
assert got.ngff.units == ref.ngff.units == {'y':'micrometer','x':'micrometer'}
assert [c.label for c in got.ngff.channels] == ['Cy3']
import numpy as np; np.testing.assert_allclose(got['y'].values[:3], [0,1.6,3.2])
print('bioio adapter matches open_ngff_dataset ✓')
"
```

Property-test idea (tier 1): for any store `ome-zarr-hypothesis` can generate and
`bioio-ome-zarr` can read, `from_bioio(BioImage(store))` should equal
`open_ngff_dataset(store)` (dims, coords, units, channels, carrier). Reuse the
harness in `tests/test_property_rules.py`.

## Suggested opening prompt

"Read `notes/handoff-bioio-adapter.md`. Build `xarray_ngff.adapters.bioio.from_bioio`
starting with tier 1 (recover the `ome` block from bioio's `attrs['unprocessed']`
and rebuild via the existing reader path), verified against `open_ngff_dataset`
on the idr0066 store. Then discuss tier-2 (non-OME-Zarr) scope."
