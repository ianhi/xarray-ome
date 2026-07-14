# Things learned — hard problems in mapping NGFF → xarray

A running list of the genuinely *hard* problems we've hit mapping OME-Zarr (NGFF)
onto xarray. Written as talk material: each section is a surprise/trap, the
mechanism underneath, and how it resolves. Living doc — add as we find more.

Companion artifacts: `experiments/` (worked examples), `research/` (the RFC book),
`notes/upstream-ideas.md` (fixes that belong in xarray itself).

---

## 1. Lazy vs materialized coordinates

**The trap.** OME-Zarr stores coordinates *implicitly* as a `scale`+`translation`
per axis. In xarray you need actual coordinate values for `.sel` to work in
physical units. The obvious move — materialize `x = translation + scale·arange(N)`
— feels wasteful, so you reach for a *lazy* coordinate (compute on demand). Then
you discover you can't have everything.

**The three-way tension.** For a regular (diagonal) axis you want three things,
and today's xarray built-ins give you any *two*:

| approach | lazy? | built-in? | `.sel(x=slice(...))`? |
|---|---|---|---|
| dense array → `PandasIndex` | ❌ | ✅ | ✅ full grammar |
| built-in `RangeIndex` | ✅ | ✅ | ❌ *nearest only* |
| built-in `CoordinateTransformIndex` | ✅ | ✅ | ❌ *point-wise only* |
| our `SliceableTransformIndex` subclass | ✅ | (built on built-in) | ✅ |

Both lazy built-in indexes **reject label slices** — `RangeIndex.sel` raises
"only supports method='nearest'", `CoordinateTransformIndex.sel` "only supports
advanced (point-wise) indexing." And slice selection *is* the multiscale payoff:
one `tree.sel(x=slice(0,4))` in world units must return the right pixels at every
resolution level.

**The insight.** A slice on an *invertible* transform is trivially resolvable —
map the two endpoints through `transform.reverse()`, ceil/floor to inclusive
integer bounds, done. The built-in just never implemented it. A ~20-line
`CoordinateTransformIndex` subclass adds scalar + slice `sel`, stays lazy, and
generalizes to any invertible 1-D transform (affine, log, time-base). → parked as
an xarray upstream contribution (`notes/upstream-ideas.md`).

**The real punchline (the part worth saying out loud).** We went looking for a
reason *lazy beats materialized* — and mostly didn't find one. It isn't a memory
decision: a coordinate is `N × 8` bytes,

| image type | largest axis | dense coord |
|---|---|---|
| confocal / widefield frame | 2,048 | 16 KB |
| light-sheet volume (long axis) | 10,000 | 78 KB |
| whole-slide histopathology @40× | 100,000 | 781 KB |
| whole fly-brain EM mosaic (FAFB) | 250,000 | 1.9 MB |

and even a whole-brain axis is ~2 MB, nothing beside GB–TB of pixels. And it isn't
a round-trip decision either: a regular axis is *linear*, so recovering
`scale`/`translation` from a dense array is exact (`scale = x[1]-x[0]`,
`translation = x[0]`) — dense loses nothing. So for the regular (diagonal) axis
the honest answer is: **materialize it and move on.**

Where the transform-backed coordinate *does* earn its place is not the diagonal
case at all — it's that the **same machinery is forced on us by the non-separable
cases** (§2): a lens has no dense 1-D coordinate you could materialize. So the real
design question is "do I want *one* coordinate mechanism across the whole transform
taxonomy, or a cheap special-case for the diagonal axis and a different one for
everything else?" That's a consistency argument, not a performance one.

And the genuinely surprising finding along the way: **the built-in *lazy* indexes
can't slice at all** — that's the real gap, independent of dense-vs-lazy.

*Demo:* `experiments/lazy_vs_dense_coords.ipynb` — both approaches, identical
`.sel` results, side by side.

---

## 2. Non-separable & non-invertible transforms (the RFC-5 wall)

**The trap.** Diagonal `scale`+`translation` is the easy 1% — one 1-D coordinate
per axis. The moment a transform is a general affine, a shear, or a lens, the
physical position of a pixel depends on *more than one* pixel index. There is no
1-D coordinate to attach; you need full **2-D/N-D coordinate arrays** `x(y,x)`,
`y(y,x)`. xarray's default `PandasIndex` can't index those.

**Two walls, escalating:**
- *Non-separable but invertible* (general affine, closed-form fisheye): a custom
  `CoordinateTransform` with `forward` (lazy N-D coords) + `reverse` gives **exact**
  `.sel` via `CoordinateTransformIndex`. Still clean.
- *No analytic inverse* (real lens / displacement field): you can push pixels
  forward into world space but can't invert. `.sel` degrades to a **KD-tree
  nearest-neighbour** search (`NDPointIndex`) — *approximate* selection. This is
  the genuine ceiling; there's no exact answer to give.

**The lesson.** The right xarray index is a direct function of two spec
properties: *separable?* and *invertible?*. That 2×2 is the whole taxonomy.

*Demos:* `experiments/{lens,scape,registration,stitched}_index.ipynb`; the
building blocks in `xarray_ome/indexes/`. Also the xarray tutorial's fisheye
example (`intermediate/indexing/why-an-index.ipynb`) is the clean closed-form case.

---

## 3. DataTree coordinate inheritance fights the pyramid

**The trap.** "A pyramid is a tree of shared metadata → put the coordinates on the
root and let children inherit them." This is backwards and it *raises*.

**The mechanism.** xarray attaches inherited coordinates by aligning each child
against the parent with `join="exact"`. The entire point of a resolution pyramid
is that `y`/`x` have *different lengths* at each level, so a `y`/`x` coordinate on
the root throws `ValueError` the instant a downsampled child is attached.

**The rule that works:**

| axis | length across levels | placement |
|---|---|---|
| `c`, `t` | constant | may live on root, inherited |
| `z`, `y`, `x` | shrinks per level | **local to each level** |

**The nice payoff.** With per-level physical coords, `DataTree.sel` in *world*
units just works: one `tree.sel(x=slice(0,4))` resolves the same physical span at
each level's own resolution (verified: 5 px @ level0, 3 px @ level1 for a 0–4
span). Whereas `.isel(x=3)` is *meaningless* across a pyramid — same integer index
= a different physical point at every level.

**The limit.** You cannot make cross-level logic ("give me the coarsest level with
≥512 px") an *index* — `IndexSelResult` can't reach another node and `DataTree.sel`
indexes each node independently. That has to be an accessor method, not an index.

---

## 4. Lossless round-trip & forward-compat (the carrier problem)

**The trap.** "Parse the metadata into nice typed objects, write them back out."
You silently drop every field your parser didn't model — including future spec
fields and vendor extensions. `ngff-zarr` alone is empirically lossy this way.

**The fix.** Keep the raw `attributes.ome` block verbatim as a **carrier**,
regenerate only the *managed* fields from xarray state on write, and **deep-merge**
them over the carrier. Testable guarantee: `open → write` with no edits reproduces
`attributes.ome` byte-for-byte (modulo key order); edits touch only edited fields.

**Connects to #1:** re-deriving `scale`/`translation` from a materialized
coordinate array on write is itself a lossy step — another argument for keeping the
transform *rule* (lazy coord) rather than a sampled array.

---

## 5. Real NGFF data is buggy — the mapping must be defensive

Worked RFC-5 example stores fought us in ways worth showing (reality ≠ spec):
- Compressor declared `"zstandard"` but the zarr v3 codec name is `"zstd"` — zarr
  can't open the store without a codec-name alias.
- Version string `"0.6.dev1"` → `ngff-zarr` 0.37 *rejects* it, so even though it
  now models RFC-5 it can't read these specific stores.
- Stitched-tile translation vectors stored in array-axis order `(y,x)`, not the
  world CS order `(x,y)` — pairing by world order silently scrambles the mosaic.
- The lens transform ships `input=corrected, output=raw` (physical→sensor) with
  **no inverse**; placing raw pixels in the corrected frame needs an inversion the
  store doesn't provide.

**The lesson.** "Never loses data" and "robust to user mistakes" aren't just about
the happy path — the format in the wild has defects the mapping has to absorb.

**Also:** `ngff-zarr` models only *linear* transforms even at 0.37 (`Identity,
Scale, Translation, Rotation, Affine, TransformSequence`) — no typed
`displacements`/`bijection`. So field-based cases (lens, registration) will always
need raw array reads, even once the version/codec issues are fixed.

---

## 6. The "attrs are fragile" argument is overstated

Early on we leaned on "you can't trust xarray `attrs` to survive operations."
Checking it: modern xarray **keeps** attrs through reductions, elementwise ops, and
slicing, and attrs round-trip losslessly through Zarr v3. The real loss vectors are
narrow and specific — worth stating *precisely* rather than as blanket fragility
(and there's precedent: rioxarray keeps CRS/metadata on a coordinate). Overstating
it weakens an otherwise-good argument.

**But the precise loss vectors are real (measured on xarray 2026.7.0), and they
bit us.** Two are *structural* — no `keep_attrs` toggle touches them:

1. **Extraction drops dataset-level attrs.** `ds["image"]` returns the *variable's*
   attrs, never the Dataset's — so a carrier in `ds.attrs["ome"]` does **not** ride
   along to the DataArray. (`keep_attrs` governs *operations* — reductions,
   elementwise, slicing — where modern xarray does keep attrs; it says nothing
   about pulling a variable out of a Dataset.)
2. **DataTree inherits coordinates, not attrs.** A level pulled off a pyramid
   (`dt["0"].to_dataset()`) carries none of the root's `attrs["ome"]`.

So `stack → dataset → image` silently strips the carrier, and `.ngff` on the
result reported *nothing* — even though the physical info was sitting right there
on the coordinates.

**The design consequence (the real lesson).** The durable channel is the
**coordinate**, not the dataset-level carrier. `x.attrs["units"]` and the
`TransformIndex` (scale/translation) *do* survive extraction to a bare DataArray —
so `.sel` in microns still works on `ds["image"]`. Therefore:
(a) push physical info onto coordinates (units as CF coord attrs, transform-backed
coords) — the design already does this;
(b) stamp the verbatim carrier on **every** pyramid node, not just the root (else
`dt["0"].ngff` reads empty) — fixed in the reader;
(c) make the `.ngff` accessor **reconstruct** axes / units / calibrated from the
coordinates when the carrier is missing, and register it on `DataArray` too — so
what the accessor reports matches what a pipeline actually preserves. Reserve the
carrier for genuinely dataset-level fields (omero channels, version, unknown
forward-compat blocks).

The talk framing: *"attrs are fragile" is overstated for operations but exactly
right for extraction — so lean on coordinates, and treat the carrier as
best-effort context, not the source of truth.*

---

*Add sections as we hit new walls.*
