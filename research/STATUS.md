# Research Book Status

## Goals

We're building a jupyter-book under `research/` that documents the NGFF 0.5 → xarray mapping, **leading to an RFC** (the writing is the deliverable; the `xarray_ngff` library is an optional reference implementation). The book has four content parts plus intro/conclusion: NGFF Spec, xarray Data Model, Custom Indexes, The Mapping.

### Design Requirements

1. **Robust to user mistakes** — no raw dicts in attrs; the API makes wrong things hard.
2. **Usable for developers** — structured, typed, discoverable.
3. **Never loses data** — full round-trip fidelity including unknown/future fields.

## Current State (updated 2026-06-08)

### Every content page now has real, mutually-consistent content

- **Spec section** — `zarr-v3`, `coordinate-transformations`, `multiscales`, `omero` (all written); `axes.ipynb` + `axes-experiments.ipynb` (notebooks, complete).
- **xarray section** — `data-model`, `datatree`, `encoding` (all written from the deep-dive research).
- **Custom Indexes section** — `index-overview`, `range-index`, `coordinate-transform-index`, `linked-indexes` (all written).
- **Mapping section (the RFC core)** — `axes-to-dims`, `transforms-to-coords`, `multiscales-to-datatree`, `omero-to-coords`, `round-trip`, `custom-index-design` (all written, recommend + rejected-alternatives form).
- **`summary.md`** — the consolidated proposed mapping / RFC synthesis (written).

Book builds clean: `uvx jupyter-book build` → 23 pages, no broken crosslinks (only advisory `{doc}`-style warnings).

### Decisions locked (this session)

- **RFC posture**: recommend + document rejected alternatives.
- **Typed layer**: use **ngff-zarr** (one dependency, already our foundation) — but it is empirically **lossy alone**, so wrap it with a **raw-`zarr.json` carrier** that preserves unknown fields and is deep-merged on write (custom backend controls read+write).
- **API is layered**: `.ngff` accessor = public *front door* only (read/build/cross-level select); persistence = native xarray + carrier; validation = typed model; selection = plain coords now, `RangeIndex`-style index as the target.
- **axes**: `name`→dim verbatim (no TCZYX coercion); `type`/`unit`→coord attrs (`axis_type`/`units`) via accessor.
- **transforms**: materialise dense 1-D coords (a read-view) + preserve raw transforms in carrier; never re-derive `(s,t)` on write.
- **multiscales**: DataTree, one node/level; spatial coords **local** per level (inheritance fights the pyramid); only `c`/`t` inherited.
- **omero**: `label`→`c` dimension coordinate; color/window/rest→carrier via accessor.

### Key correction made to existing material

The axes notebook's **"attrs are fragile"** argument is **overstated** — modern xarray keeps attrs through reductions/elementwise/slicing, and attrs round-trip losslessly through Zarr v3. The mapping pages now use the *precise* (narrow) loss vectors + the rioxarray "metadata-on-a-coordinate" precedent instead.

## Field Research (all in `notes/field-research/`)

`ome-zarr-libraries`, `spatialdata-and-multiscale`, `bioio`, `xarray-ecosystem-analogies`, `ngff-spec-status`, `internal-gap-analysis`, `xarray-data-model-surface`, `xarray-indexes-deep`, `xarray-datatree-deep`, `ngff-zarr-roundtrip-verification`. Six libraries surveyed; xarray surface mapped against the source; ngff-zarr round-trip verified empirically.

## What Needs Doing Next

1. ~~**Reframe `spec/axes.ipynb`**~~ — **DONE.** The notebook now leads with the recommendation (Alternative A, CF-style coord attrs), relabels B as the rejected finalist, corrects the overstated "attrs are fragile" framing to the narrow loss vectors (matching `mapping/axes-to-dims.md`), and converts the "Open questions" section to "Resolved decisions" with links. The full executable A-vs-B comparison is retained as evidence.
2. ~~**Promote/assemble the RFC document**~~ — **DONE.** Decision: **the book *is* the RFC** (no standalone `rfc.md`). `intro.md` reframed as RFC front matter (abstract, motivation, goals, scope, how-to-read); `summary.md` promoted to position #2 as "The Proposal" (with the reference-implementation section rewritten to cite the built, **property-tested** package); TOC reordered to **proposal → The Mapping (core) → Appendices** (spec, xarray, indexes, prior-art); project retitled `xarray-ngff RFC: An xarray representation for OME-Zarr (NGFF 0.5)`.
3. ~~**Align the reference implementation**~~ — **DONE.** `xarray_ngff/` is now the carrier + `.ngff` accessor + deep-merge design (committed), with a property-test suite proving the four core rules. `docs/metadata_mapping.md` has also been rewritten to the current design (describes the `.ngff` accessor + carrier; the old per-field approach is noted as removed).
4. ~~**Optional polish**~~ — **DONE.** All 142 `{doc}` roles across the book were converted to markdown links (`[](path.ext)`, with `.md`/`.ipynb` resolved per target), and the stray `spec/coordinate-transformations.md` → `prior-art` ref was pointed at `../prior-art.md`. The book now builds with **zero content warnings** (only an unrelated Node `url.parse` deprecation from the myst tooling).

### Consistency locked (this session)

- **Accessor name is uniform: `.ngff`** everywhere (matches what the package registers — `@register_dataset_accessor("ngff")`). All book prose was migrated from the older `.ome` accessor name; `attributes.ome` (the on-disk zarr.json namespace), `.ome.zarr` (store extension), and `engine="ome-zarr"` (the backend engine id) are deliberately unchanged.
- Book builds clean (`uvx jupyter-book build --html`): 23 pages, no broken crosslinks — only the advisory `{doc}`-role warnings remain (item 4).

## Key Local Repo Paths

| Resource | Path |
|----------|------|
| xarray source | `/Users/ian/Documents/dev/xarray/` |
| RangeIndex | `/Users/ian/Documents/dev/xarray/xarray/indexes/range_index.py` |
| ngff-zarr (installed) | main venv `.venv` (NOT `research/.venv`) |
| Field research | `research/../notes/field-research/` |
| Handoff document | `notes/handoff-metadata-conversion-refactor.md` |
