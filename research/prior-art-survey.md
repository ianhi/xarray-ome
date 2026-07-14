---
title: 'Prior Art: Literature & Patterns Survey'
---

_Research compiled June 2026 for the xarray-ngff RFC._
_Focus: prior art and theoretical writing on mapping the OME-NGFF (OME-Zarr, NGFF 0.5) bioimaging metadata specification onto the xarray N-dimensional array data model. Four angles: (a) mapping rich domain metadata onto generic array models; (b) lossless round-trip / forward-compatibility; (c) coordinate transforms & multiscale representation; (d) typed API design over loose dicts._

> How to read this: the **Synthesis** below is the part to read first — it threads the four angles into one argument about what prior art establishes and what the RFC must still contribute. Each angle then has its own annotated bibliography (TL;DR → ranked entries → per-angle gap verdict). The final two sections inventory our Zotero library and consolidate the RFC's open contribution. Every claim carries a primary-source URL.

---

## Synthesis: what prior art settles, and what it leaves for the RFC

The recurring shape across all four angles is the same one Unidata named decades ago: a **generic labeled-array container has no inherent domain semantics**, so domain meaning has to be layered on top (what software design calls an {term}`impedance mismatch`) — and *where* that layer lives, *how* it is typed, and *what it preserves* are the only real degrees of freedom. The NGFF↔xarray mapping is one more instance of a problem the scientific-data world has solved partially, repeatedly, and never quite completely.

Four things are **settled** by prior art and can be cited rather than invented:

1. **The "convention + accessor over a generic container" stack is the proven pattern.** CF Conventions ride on bare netCDF/Zarr attributes; cf-xarray, rioxarray, MetPy, and pint-xarray each surface a domain convention through a `.`-namespace accessor. xarray's own docs explicitly recommend accessors *over subclassing*. This directly validates the `.ngff` front-door design — it is idiomatic, not novel.
2. **The {term}`carrier / passthrough pattern` for {term}`forward-compatibility` is independently reinvented everywhere** — Protobuf unknown fields (binary), Pydantic `extra="allow"`, Rust serde `#[serde(flatten)]` — and is theoretically grounded by the W3C TAG {term}`must-ignore / must-understand` model and the (contested) robustness principle (*Postel's Law* — "be liberal in what you accept"). "Parse known fields, stash unknowns verbatim, re-emit unchanged" is a textbook move.
3. **The typed-layer-separate-from-persistence split has a clean lineage** — {term}`parse, don't validate`, {term}`make illegal states unrepresentable`, the *primitive-obsession* smell (modelling rich concepts as bare strings/dicts), and {term}`ports and adapters` (hexagonal architecture) — and a near-perfect domain exemplar in **ome-zarr-models-py**, whose Pydantic models *deliberately* "do not handle reading or writing data."
4. **Both hard sub-problems have working primitives.** xarray's `CoordinateTransformIndex` (+ `rasterix.RasterIndex`) turns an affine into lazy physical coordinates with working `.sel()`; `multiscale-spatial-image` and SpatialData already store NGFF pyramids as a DataTree, one node per level.

Three things are **not** settled — and these define the RFC's contribution:

- **The seam between the typed half and the xarray half is missing.** Every precedent solves *one* half. `ome-zarr-models-py` types the metadata but has no dims/coords bridge. cf-xarray bridges to xarray but interprets raw attrs *on access* rather than parsing into a persisted, forward-compatible typed model. **No one has combined a typed, `extra="allow"`-style forward-compatible NGFF model with the xarray dims/coords mapping behind a single accessor.**
- **Everyone leans on free-form `.attrs` as the escape hatch, and everyone admits it is lossy.** rioxarray warns `set_crs()` alone is "lossy"; SpatialData concedes "there may be some small difference between the proposed NGFF transformations storage and the SpatialData on-disk storage." The "never lose data" requirement is exactly the corner that shipping libraries have *not* turned. And the JSON-specific trap is sharp: the ecosystems that get preservation "for free" (Protobuf) do so only in *binary* — NGFF is JSON, so the carrier must be built explicitly and tested through the full `attrs → typed model → zarr.json → reload` round-trip.
- **NGFF's three hardest features have never been combined in one coherent mapping:** multiscale pyramids (DataTree), coordinate-transformation *chains/graphs* (RFC-5), and omero/channel metadata. DataTree is a natural home for pyramids — each level is a sibling node, and alignment is enforced only *vertically* (node vs. ancestor), so levels of different sizes coexist freely; the one discipline is keeping each level's spatial coords *local* rather than on a shared ancestor. What no DataTree-based tool yet does is back each level's coords with a *transform index* **and** model RFC-5's multi-coordinate-system graph.

**The seam, made visible.** The gap is clearest as a capability matrix — every precedent fills some columns and leaves others empty; the RFC's target row is the first to fill all of them:

| Precedent | Typed model | xarray dims/coords bridge | Lossless round-trip | Multiscale (DataTree) | Transform graph (RFC-5) |
|---|:---:|:---:|:---:|:---:|:---:|
| **ome-zarr-models-py** | ✅ | ❌ | ⚠️ needs `extra="allow"` | ❌ | ❌ (0.4/0.5 only) |
| **cf-xarray** | ❌ interpret-on-access | ✅ | ❌ | ❌ | ❌ |
| **SpatialData** | ✅ (in `.attrs`) | ✅ | ⚠️ "approximate" | ✅ | ✅ graph |
| **multiscale-spatial-image** | ❌ | ✅ | ⚠️ attrs transforms | ✅ | ❌ |
| **rasterix** | n/a | ✅ affine index | n/a | ❌ per-array | ❌ |
| **bioio / AICSImageIO** | ❌ | ✅ (fixed TCZYX) | ❌ | ❌ | ❌ |
| **→ This RFC (target)** | ✅ | ✅ | ✅ verbatim carrier | ✅ local coords/level | ✅ forward-compat |

_Legend: ✅ covered · ⚠️ partial/caveated · ❌ absent. "Lossless round-trip" = preserves unknown/future NGFF fields verbatim. RFC-5 = NGFF's draft coordinate-systems/transformations spec (see Angle C, entry E)._

**Bottom-line verdict:** the RFC is not inventing primitives — it is performing a *synthesis* the ecosystem has been circling. Its defensible novelty is the combination: a typed, lossless, forward-compatible NGFF model whose transforms become `CoordinateTransformIndex`-backed coordinates on a one-node-per-level DataTree, surfaced through an `.ngff` accessor, with a JSON carrier for unknown fields. The two closest designs to study and borrow from are **SpatialData** (typed transform graph + DataTree pyramids, but attrs-based and only "approximately" round-trip-safe) and **rasterix** (slice-aware affine recomputation on `CoordinateTransformIndex`).

---

# Angle A — Mapping rich domain metadata onto generic array models

## TL;DR

- **The foundational statement of the problem is Unidata's:** "netCDF itself has no inherent semantics; while coordinates can be stored in variables and described by attributes, the meanings of these variables and attributes and relationships between them are not defined by netCDF" ([Unidata CDM docs](https://docs.unidata.ucar.edu/netcdf-java/dev/userguide/common_data_model_overview.html)).
- **The dominant pattern is "convention-on-a-generic-container + accessor"**: CF Conventions ride bare netCDF/xarray attrs; cf-xarray surfaces them via a `.cf` namespace — exactly the layered approach the RFC favors ([cf-xarray](https://cf-xarray.readthedocs.io/)).
- **SpatialData (scverse) is the closest direct prior art**: it maps OME-NGFF onto `xarray.DataArray` + AnnData, decided transform metadata lives in `.attrs` (NOT xarray coordinates), and maintains *two* transform class hierarchies (NGFF-strict vs. operational) to absorb the impedance mismatch ([SpatialData design doc](https://spatialdata.scverse.org/en/latest/design_doc.html)).
- **The OME community has already debated xarray compatibility directly** (`ome/ngff#48`): explicit 1D coordinate arrays (xarray-natural, good for slicing/viz) vs. concise scale/translation transforms (NGFF-native) — the exact axes-vs-coords decision in our notes ([ome/ngff#48](https://github.com/ome/ngff/issues/48)).
- **GeoZarr is a live parallel**: a rich geospatial spec on Zarr that *deliberately keeps CF attributes unprefixed* so xarray/cfgrib keep working unmodified — a concrete "don't break the generic-container tooling" principle ([GeoZarr CHARTER](https://github.com/zarr-developers/geozarr-spec/blob/main/CHARTER.adoc)).
- **STAC solves a different layer**: `datacube`/`xarray-assets` extensions describe dimensions/variables in *catalog* metadata, external to the array — prior art for "where domain metadata lives when the container is too generic" ([stac-extensions/datacube](https://github.com/stac-extensions/datacube)).
- **Everyone uses `attrs` as the escape hatch and admits it is fragile**: rioxarray explicitly warns `rio.set_crs()` is "lossy" unless written into coordinate attrs ([rioxarray](https://corteva.github.io/rioxarray/stable/getting_started/crs_management.html)).
- **No prior art covers multiscale pyramids + a typed, round-trip-safe NGFF transform model on xarray DataTree** — bio-imaging libs (bioio, ome-zarr-py) expose flat TCZYX arrays with thin metadata and admit "improvements in the metadata support are needed."

### A. SpatialData: an open and universal data framework for spatial omics (2024)
**Links:** https://www.nature.com/articles/s41592-024-02212-x · https://spatialdata.scverse.org/en/latest/design_doc.html · https://github.com/scverse/spatialdata
**Author/Org:** Marconato et al., scverse
**Year:** 2024
**Summary:** Represents spatial-omics data as standard `xarray.DataArray`/AnnData/GeoPandas/Dask objects "with specified metadata," inheriting OME-NGFF for raster storage. Coordinate systems and transforms live in each element's `.attrs`, and "the xarray coordinates are not saved in the NGFF storage." Maintains two transform hierarchies — NGFF-compliant `NgffBaseTransformations` and operational `BaseTransformation`.
**Relevance to NGFF↔xarray:** The most direct precedent — a shipping library mapping NGFF onto xarray. Transforms-in-`.attrs` (vs. materialized coordinates) is exactly the alternative the RFC weighs; the dual transform-class design is a concrete pattern for spec-strictness vs. usability.
**What it's missing / limitations:** Not a clean typed accessor over plain xarray; metadata-in-attrs is a raw-dict approach (violates requirement #1); round-trip fidelity admitted as imperfect.
**Depth:** deep-technical
**Quality:** Highest-value entry; peer-reviewed plus a public design doc with explicit rationale.

### B. cf-xarray: an accessor that interprets CF attributes (2021–)
**Links:** https://cf-xarray.readthedocs.io/ · https://earthcube2021.github.io/ec21_book/notebooks/ec21_cherian_etal/DC_01_cf-xarray.html · https://github.com/xarray-contrib/cf-xarray
**Author/Org:** Cherian, Bourbeau et al. / xarray-contrib
**Year:** 2021 (EarthCube notebook); ongoing
**Summary:** Uses xarray's accessor (`.cf`) to interpret CF Convention attributes already present on objects, mapping standardized CF names to dataset-specific variable names so users write `ds.cf.mean("longitude")` without knowing arbitrary variable names.
**Relevance to NGFF↔xarray:** The canonical model for the recommended architecture — a thin domain-aware accessor over a generic container. Directly supports "accessor as typed front door" and the two-level name lookup needed for NGFF's three `space` axes.
**What it's missing / limitations:** CF is flat; no multiscale, no transform chains, no round-trip/forward-compat guarantee; reads attrs but doesn't enforce a typed schema on write.
**Depth:** accessible (notebook) + deep-technical (source)
**Quality:** Excellent, mature, widely adopted reference implementation of the pattern.

### C. ome/ngff#48 — "Compatibility with xarray" (issue discussion)
**Links:** https://github.com/ome/ngff/issues/48
**Author/Org:** OME / NGFF community
**Year:** ~2020–2021
**Summary:** Proposes making OME-Zarr compatible with `xarray.Dataset.to_zarr()` using x/y/z/c/t as explicit dims. The author explored avoiding explicit coordinates in favor of "concise spatial-dimension rank spacing/scale, origin/translation" but found explicit 1D coordinate arrays advantageous for "natural slicing operations" and visualization.
**Relevance to NGFF↔xarray:** The OME community wrestling with our exact decision — explicit coordinates vs. scale/translation transforms. Documents the trade-off the RFC must adjudicate.
**What it's missing / limitations:** Informal, partly historical; predates NGFF 0.5 and DataTree; exploratory, not normative.
**Depth:** deep-technical (design discussion)
**Quality:** Primary-source design debate; invaluable context though unsettled.

### D. GeoZarr spec — Charter and CF relationship (2022–)
**Links:** https://github.com/zarr-developers/geozarr-spec/blob/main/CHARTER.adoc · https://hackmd.io/@geozarr/Sk-wb34O-e
**Author/Org:** zarr-developers / GeoZarr working group
**Year:** 2022–ongoing
**Summary:** Layers a geospatial data model on Zarr, building on CF for metadata and grid-mapping (CF's convention for storing a coordinate reference system in a sidecar variable) for CRS. Explicit principle: "CF deliberately uses unprefixed attributes so existing CF-compliant Zarr datasets (and libraries like xarray, cf-python, cfgrib) continue to work without modification."
**Relevance to NGFF↔xarray:** A live, contemporaneous parallel — another opinionated domain spec on Zarr — with an explicit stance on *not breaking generic-container tooling*. Directly applicable to how NGFF's `ome` namespace surfaces (or doesn't) to xarray.
**What it's missing / limitations:** Geospatial CRS concerns differ from NGFF's multiscale + transform-chain + omero model; inherits CF's flat-attr approach, not a typed object model.
**Depth:** spec
**Quality:** Authoritative, actively developed; the closest sibling spec to NGFF.

### E. Unidata Common Data Model & netCDF Attribute Conventions
**Links:** https://docs.unidata.ucar.edu/netcdf-java/dev/userguide/common_data_model_overview.html · https://docs.unidata.ucar.edu/nug/current/attribute_conventions.html
**Author/Org:** Unidata / UCAR
**Year:** ongoing
**Summary:** The CDM defines three stacked layers adding "successively richer semantics": a syntactic data-access layer, a coordinate-system layer, and a scientific-data-type layer. Explicit that "netCDF itself has no inherent semantics."
**Relevance to NGFF↔xarray:** The original articulation of the semantic-gap problem *and* the layered solution the RFC adopts. NGFF↔xarray essentially adds an NGFF-flavored "scientific data type layer" above xarray's coordinate layer.
**What it's missing / limitations:** Model/philosophy, not an NGFF implementation; predates Zarr; no multiscale, forward-compat, or typed-API guidance.
**Depth:** spec / deep-technical
**Quality:** Foundational and authoritative; the conceptual bedrock.

### F. xarray: N-D labeled Arrays and Datasets in Python (2017)
**Links:** https://openresearchsoftware.metajnl.com/articles/10.5334/jors.148 · https://doi.org/10.5334/jors.148
**Author/Org:** Stephan Hoyer & Joe Hamman, JORS
**Year:** 2017
**Summary:** The canonical description of the xarray data model — N-D labeled arrays combining a pandas-like API with Unidata's CDM — establishing dims, coords, and attrs as the core constructs.
**Relevance to NGFF↔xarray:** Defines the target container; the explicit CDM lineage justifies treating NGFF as another CDM-style convention. The dims/coords/attrs trichotomy is the surface NGFF must project onto.
**What it's missing / limitations:** Domain-agnostic; attrs documented as a metadata dumping ground with no schema or round-trip guarantee; predates DataTree.
**Depth:** spec / accessible
**Quality:** Definitive primary source for the xarray side.

### G. STAC datacube & xarray-assets extensions
**Links:** https://github.com/stac-extensions/datacube · https://github.com/stac-extensions/xarray-assets · https://pystac.readthedocs.io/en/stable/api/extensions/datacube.html
**Author/Org:** STAC community / stac-extensions
**Year:** ongoing
**Summary:** The Datacube extension describes a cube's dimensions/variables (`cube:dimensions`, `cube:variables`) in *catalog* metadata; xarray-assets records how to open an asset with xarray. Metadata about the array lives external to the array container.
**Relevance to NGFF↔xarray:** Prior art for "where does domain metadata live when the container is too generic?" — STAC's answer is *outside* the array, in a sidecar catalog. A useful contrast to the RFC's decision to keep metadata in-store but typed.
**What it's missing / limitations:** Discovery/catalog metadata, not in-array semantics; doesn't solve in-store round-tripping of transforms or multiscale structure.
**Depth:** spec
**Quality:** Solid, widely used; tangential but clarifies the "metadata locus" design axis.

### H. rioxarray CRS/metadata management
**Links:** https://corteva.github.io/rioxarray/stable/getting_started/crs_management.html · https://github.com/corteva/rioxarray/issues/882
**Author/Org:** corteva / rioxarray
**Year:** ongoing
**Summary:** Stores CRS as a CF grid-mapping coordinate (`spatial_ref` with `crs_wkt`/`GeoTransform` attrs), resolving in order encoding → `grid_mapping` coord → `crs` attr → data_vars. Warns that "calling only `rio.set_crs()` is lossy and will not modify the Dataset/DataArray metadata."
**Relevance to NGFF↔xarray:** A widely used example of attaching rich domain metadata to xarray via a dedicated coordinate + attrs, with an explicit ordered resolution strategy — a model for how an NGFF accessor locates/persists transform metadata. The "lossy" warning vividly illustrates requirement #3.
**What it's missing / limitations:** Single-concern (CRS), CF-grid-mapping-specific, relies on droppable free-form attrs/encoding.
**Depth:** deep-technical / accessible
**Quality:** Pragmatic, battle-tested reference for coordinate-attr metadata patterns.

### I. OME-NGFF papers: Moore et al. 2021 (Nat Methods) & 2023 community update
**Links:** https://www.nature.com/articles/s41592-021-01326-w · https://www.ncbi.nlm.nih.gov/pmc/articles/PMC10492740/ · https://www.biorxiv.org/content/10.1101/2021.03.31.437929v4
**Author/Org:** Moore, Allan, Besson, Burel et al. / OME
**Year:** 2021, 2023
**Summary:** Establishes the NGFF rationale: no single format fits all bioimaging use cases, so a Zarr-based cloud-native format with a *common metadata model* is proposed to deliver FAIR data.
**Relevance to NGFF↔xarray:** Defines the domain spec we map *from* and its cross-environment interoperability goal — the mandate for an xarray mapping. "No single structure fits all" is itself an argument for a typed accessor layer.
**What it's missing / limitations:** Describes the format and goals, not any xarray mapping; predates detailed transform specs; no Python data-model guidance.
**Depth:** spec / accessible
**Quality:** Authoritative for the NGFF side; essential framing, not a mapping recipe.

### J. bioio / bioio-ome-zarr / AICSImageIO
**Links:** https://github.com/bioio-devs/bioio · https://github.com/bioio-devs/bioio-ome-zarr · https://allencellmodeling.github.io/aicsimageio/ · https://github.com/ome/ome-zarr-py/issues/407
**Author/Org:** bioio-devs / Allen Institute / OME
**Year:** ongoing
**Summary:** bioio exposes an `xarray_data` property returning a 5D TCZYX `DataArray`, populating coordinates "if bioio finds coordinate information." Builds on ome-zarr-py. Maintainers note conversion is possible "though improvements in the metadata support are needed."
**Relevance to NGFF↔xarray:** The current de facto bio-imaging approach — fixed TCZYX with thin, best-effort coordinates — and its candidly acknowledged limits. The baseline the RFC aims to improve on.
**What it's missing / limitations:** Rigid TCZYX, no DataTree multiscale view, no typed round-trip of transforms/omero metadata.
**Depth:** deep-technical (docs/source)
**Quality:** Useful as the practical baseline; an ad-hoc bridge, not a designed mapping.

## Gap verdict — Angle A
Prior art robustly establishes the *pattern* (generic container + accessor or sidecar catalog), and SpatialData and `ome/ngff#48` tackle NGFF-on-xarray directly. But every precedent leans on free-form `.attrs` openly admitted to be lossy (rioxarray) or only approximately round-trippable (SpatialData), and none provides a *typed, schema-enforced, forward-compatible* model preserving unknown NGFF fields. No prior work combines NGFF's three hardest features — multiscale pyramids (DataTree), transform chains, and omero/channel metadata — into one round-trip-safe mapping.

---

# Angle B — Lossless round-trip / forward-compatibility

## TL;DR

- **Protocol Buffers' binary wire format preserves unknown fields verbatim** as (field number, wire type, raw bytes) and re-emits them — the canonical carrier/passthrough pattern; proto3 removed this early then restored it in v3.5 due to real-world demand ([kmcd.dev](https://kmcd.dev/posts/protobuf-unknown-fields/), [protobuf.dev](https://protobuf.dev/best-practices/dos-donts/)).
- **The decisive caveat: Protobuf preserves unknowns only in binary — converting to JSON drops them.** NGFF metadata IS JSON, so the "free" preservation does not transfer; the carrier must be built explicitly ([kmcd.dev](https://kmcd.dev/posts/protobuf-unknown-fields/)).
- **Pydantic `extra="allow"` is the closest off-the-shelf JSON carrier:** unknown keys land in `__pydantic_extra__` and round-trip through `model_dump()` — but no validation is applied to them ([Pydantic docs](https://docs.pydantic.dev/latest/concepts/models/)).
- **Rust serde `#[serde(flatten)] extra: HashMap<String, Value>` is the same pattern, and is mutually exclusive with `deny_unknown_fields`** — a sharp lesson: you cannot simultaneously reject AND preserve unknowns ([serde.rs](https://serde.rs/attr-flatten.html)).
- **The W3C TAG "must-ignore" rule (Orchard) is the governing theory:** compatible forward-evolution requires consumers to ignore-and-preserve unrecognized content, with optional "must-understand" flags ([W3C TAG](https://www.w3.org/2001/tag/doc/versioning.html), [SOAP 1.2](https://www.w3.org/TR/2007/REC-soap12-part1-20070427/)).
- **The robustness principle is now contested:** Allman (ACM Queue 2011) and Thomson (IETF draft) argue liberal *acceptance* entrenches errors — implying preservation should be *verbatim and unjudged*, not *interpretive* ([ACM Queue](https://queue.acm.org/detail.cfm?id=1999945), [IETF](https://www.ietf.org/archive/id/draft-iab-protocol-maintenance-05.html)).
- **Avro resolves writer-vs-reader schemas with defaults/aliases but discards writer-only fields not in the reader schema** — a contrasting model that does NOT preserve unknowns by default ([Avro spec](https://avro.apache.org/docs/1.11.1/specification/)).
- **OpenAPI `x-` extensions and JSON Schema `additionalProperties` are the dominant spec-level conventions** for sanctioning unknown/future fields without breaking validators ([OpenAPI 3.1](https://spec.openapis.org/oas/v3.1.0.html)).

**Figure B-1 — The carrier / passthrough round-trip.** Known fields parse into the typed model; unknown/future fields are stashed verbatim in a carrier and re-merged on write. Drop the carrier (the default in most JSON tooling) and the dashed path is where data is silently lost.

```{mermaid}
flowchart LR
    z1[("zarr.json<br/>attrs (NGFF)")] -->|parse| P{{split}}
    P -->|known fields| TM["Typed NGFF model<br/>(validated)"]
    P -->|unknown / future fields| CAR["Carrier<br/>(raw, verbatim)"]
    TM --> XR["xarray object<br/>dims · coords · attrs"]
    CAR -. carried alongside .-> XR
    XR -->|write| M{{deep-merge}}
    M --> z2[("zarr.json<br/>lossless round-trip")]
    P -.->|carrier dropped| LOSS["❌ unknown fields lost<br/>(JSON has no free preservation)"]
    style LOSS fill:#fdd,stroke:#c00
    style CAR fill:#dfd,stroke:#0a0
```

### A. The Harmful Consequences of the Robustness Principle (draft-iab-protocol-maintenance) (2018–)
**Links:** https://www.ietf.org/archive/id/draft-iab-protocol-maintenance-05.html · https://datatracker.ietf.org/doc/draft-iab-protocol-maintenance/
**Author/Org:** Martin Thomson (Mozilla) / IETF IAB
**Year:** ongoing draft
**Summary:** Argues Postel's "be liberal in what you accept" creates a feedback loop where lenient parsers normalize errors that become entrenched de-facto requirements. Recommends active maintenance and reducing ambiguity over open-ended tolerance.
**Relevance to NGFF↔xarray:** A crucial nuance for "never lose data": preservation should be *verbatim field carry-through*, NOT liberal *interpretation*. The carrier pattern (store raw, re-emit unchanged) sidesteps Thomson's critique because the typed layer never tries to understand or normalize unknowns.
**What it's missing / limitations:** Wire-protocol/adversarial framing; bioimaging metadata is lower-stakes. No structured-document round-trip discussion.
**Depth:** spec
**Quality:** Authoritative IAB counterweight; essential framing for *how* to preserve.

### B. Extending and Versioning Languages, Part 1 (W3C TAG Finding) (2006)
**Links:** https://www.w3.org/2001/tag/doc/versioning.html
**Author/Org:** David Orchard (BEA) / W3C Technical Architecture Group
**Year:** 2006
**Summary:** The foundational theory of compatible language evolution. Defines extensibility, forward/backward compatibility, the **must-ignore** rule, the **must-understand** escape hatch, and **partial understanding** (process a subset, preserve the rest).
**Relevance to NGFF↔xarray:** Supplies the RFC's design vocabulary. Unknown fields → must-ignore (preserve + re-emit); the RFC can discuss whether any NGFF extension should carry must-understand semantics so an xarray consumer refuses rather than silently degrades.
**What it's missing / limitations:** XML/namespace-centric; predates JSON-first specs; theoretical, no reference impl.
**Depth:** spec
**Quality:** The canonical academic-grade treatment of forward-compat extensibility.

### C. Protocol Buffers — Unknown Fields & Best Practices (2024)
**Links:** https://kmcd.dev/posts/protobuf-unknown-fields/ · https://protobuf.dev/best-practices/dos-donts/
**Author/Org:** Kevin McDonald (blog) + Google / Protocol Buffers docs
**Year:** 2024
**Summary:** Protobuf's binary format stores unrecognized fields as (field number, wire type, raw bytes) and re-emits them, giving automatic round-trip preservation. Proto3 dropped this then restored it in v3.5. Critically, JSON encoders DROP unknown fields.
**Relevance to NGFF↔xarray:** The gold-standard carrier reference — and its warning is decisive: because NGFF is JSON, the "automatic" binary preservation does NOT exist for free. The backend must implement an explicit JSON carrier, not rely on serializer defaults.
**What it's missing / limitations:** Binary-only preservation; the JSON gap is exactly NGFF's situation, so it's a cautionary analogue more than a reusable mechanism.
**Depth:** deep-technical
**Quality:** Precise on wire mechanism and the JSON pitfall; highly applicable.

### D. Pydantic — `extra="allow"` and Extra-Field Handling (current)
**Links:** https://docs.pydantic.dev/latest/concepts/models/ · https://docs.pydantic.dev/latest/api/config/
**Author/Org:** Pydantic (Samuel Colvin et al.)
**Year:** v2, current
**Summary:** With `extra="allow"`, fields not matching the schema are stored in `__pydantic_extra__` and included in `model_dump()`/`model_dump_json()`, enabling round-trip. No validation on extras. Default is `ignore` (silently dropped); `forbid` raises.
**Relevance to NGFF↔xarray:** The most directly reusable off-the-shelf carrier if the typed layer is Pydantic-based (as `ome-zarr-models-py` is). The RFC should specify `extra="allow"` (NOT the dangerous default `ignore`) on every NGFF model node. **Action item:** verify `ome-zarr-models-py` sets this.
**What it's missing / limitations:** Extras untyped/unvalidated; nested unknowns preserved only if every model on the path also allows extras; emit ordering needs checking.
**Depth:** deep-technical
**Quality:** Production-grade idiomatic Python carrier; the practical front-runner.

### E. The Robustness Principle Reconsidered (2011)
**Links:** https://queue.acm.org/detail.cfm?id=1999945 · https://cacm.acm.org/practice/the-robustness-principle-reconsidered/
**Author/Org:** Eric Allman / ACM Queue & CACM
**Year:** 2011
**Summary:** Revisits Postel's Law, arguing liberal acceptance harms orderly interoperability and security; seeks a middle ground rather than wholesale rejection.
**Relevance to NGFF↔xarray:** Reinforces entry A. Supports being *strict about what it understands* (validate known fields) but *liberal-by-carry* about what it doesn't (preserve unknowns untouched) — a separation that neutralizes the robustness critique.
**What it's missing / limitations:** Network-protocol framing; no data-tooling round-trip discussion.
**Depth:** accessible
**Quality:** The seminal reconsideration; useful for nuance and citation weight.

### F. serde `#[serde(flatten)]` for Capturing Unknown Fields (current)
**Links:** https://serde.rs/attr-flatten.html · https://github.com/serde-rs/serde/issues/2176
**Author/Org:** serde-rs / David Tolnay
**Year:** current
**Summary:** A `#[serde(flatten)] extra: HashMap<String, Value>` field captures unmatched keys and re-emits them — JSON round-trip preservation in Rust. Explicitly mutually exclusive with `deny_unknown_fields`; nested flatten has known edge cases (#2176).
**Relevance to NGFF↔xarray:** Confirms the carrier pattern is idiomatic across ecosystems. The mutual-exclusivity is a sharp lesson: a node cannot both reject unexpected content AND preserve it — you must choose preserve to satisfy "never lose data."
**What it's missing / limitations:** Rust-specific; nested-flatten bugs mean deep NGFF trees need careful testing; captures untyped.
**Depth:** deep-technical
**Quality:** Authoritative cross-language confirmation with a concrete gotcha.

### G. Apache Avro — Schema Resolution / Evolution (current)
**Links:** https://avro.apache.org/docs/1.11.1/specification/
**Author/Org:** Apache Avro project
**Year:** spec, current (1.11.x)
**Summary:** Reads data using both writer and reader schemas, resolving via field defaults and aliases. Resolution targets the reader schema; writer-only fields absent from the reader are discarded.
**Relevance to NGFF↔xarray:** A valuable *contrast model*. Disciplined schema-driven evolution, but the wrong fit for "never lose data" — it discards fields the reader doesn't know, illustrating why a carrier is needed *on top of* a typed schema.
**What it's missing / limitations:** No verbatim unknown-field preservation; requires both schemas; binary-oriented.
**Depth:** spec
**Quality:** Rigorous evolution rules; instructive precisely by its limitation.

### H. SOAP 1.2 `mustUnderstand` / Processing Model (2007)
**Links:** https://www.w3.org/TR/2007/REC-soap12-part1-20070427/
**Author/Org:** W3C XML Protocol Working Group
**Year:** 2007
**Summary:** Header blocks carry a `mustUnderstand` attribute; a recipient must process a `mustUnderstand="true"` block or fail the whole message, while unflagged blocks may be ignored. Explicit in-band "mandatory vs. optional extension" signaling.
**Relevance to NGFF↔xarray:** Concrete prior art for must-understand/must-ignore *in a real spec*. If NGFF needs an extension an xarray reader cannot safely drop, this is the design template.
**What it's missing / limitations:** SOAP's heavyweight reputation; per-block granularity may be overkill; XML envelope semantics don't map cleanly to Zarr JSON attrs.
**Depth:** spec
**Quality:** The canonical concrete implementation of must-understand semantics.

### I. OpenAPI `x-` Extensions & JSON Schema `additionalProperties` (current)
**Links:** https://spec.openapis.org/oas/v3.1.0.html · https://spec.openapis.org/oas/v3.0.3.html
**Author/Org:** OpenAPI Initiative
**Year:** 3.0.3 / 3.1.0
**Summary:** Sanctions vendor/future extensions via `x-`-prefixed fields that conforming tools must tolerate; JSON Schema `additionalProperties` (default `true`) governs whether unmatched keys are permitted.
**Relevance to NGFF↔xarray:** Spec-level convention prior art. NGFF's `ome` namespace already partitions vendor metadata; the RFC can recommend `additionalProperties: true` (or a documented extension key) so validators don't reject future fields and the carrier has a sanctioned home.
**What it's missing / limitations:** A naming convention, not a preservation mechanism — tooling still must implement carry-through; silent on emit ordering.
**Depth:** spec
**Quality:** The de-facto industry convention for extension fields.

### J. ruamel.yaml round-trip mode & tomlkit (style-preserving) (current)
**Links:** https://pypi.org/project/ruamel.yaml/ · https://github.com/python-poetry/tomlkit
**Author/Org:** Anthon van der Neut (ruamel.yaml); Poetry project (tomlkit)
**Year:** current
**Summary:** ruamel.yaml's `typ='rt'` preserves comments, key order, flow style across load→edit→save (where PyYAML drops them); tomlkit preserves whitespace/comments/formatting — by attaching original presentation to specialized structures rather than discarding it.
**Relevance to NGFF↔xarray:** Demonstrates lossless round-trip in *document tooling* — fidelity requires *retaining what the parser doesn't act on*. A model for "the parsed representation must shadow-store everything not consumed."
**What it's missing / limitations:** Concerned with human-facing formatting, which Zarr JSON attrs largely lack; less about *semantic* unknown fields than presentation.
**Depth:** deep-technical
**Quality:** Strong, widely-used demonstration of the retain-the-unconsumed principle.

### K. ome-zarr-models-py (typed NGFF metadata layer) (current)
**Links:** https://github.com/ome-zarr-models/ome-zarr-models-py · https://ome-zarr-models-py.readthedocs.io/en/latest/tutorial/
**Author/Org:** ome-zarr-models org
**Year:** current (1.x requires zarr-python v3; supports OME-Zarr ≥ 0.4)
**Summary:** A minimal zarr-v3-native Pydantic package for reading/writing/validating OME-Zarr metadata — successor to pydantic-ome-ngff. Forward-compat behavior hinges on whether its models set `extra="allow"`.
**Relevance to NGFF↔xarray:** The most directly applicable *existing implementation* to evaluate as the typed layer beneath the `.ngff` accessor. **Action item:** verify each model's `extra` setting; if any default to `ignore`/`forbid`, unknown NGFF fields are silently dropped and "never lose data" fails.
**What it's missing / limitations:** `extra="allow"` not confirmed throughout — must be verified in source before relying on it (flagged in project memory).
**Depth:** deep-technical
**Quality:** The most relevant concrete reference implementation; preservation behavior unverified.

## Gap verdict — Angle B
The carrier/passthrough pattern is independently reinvented across Protobuf (binary), Pydantic `extra="allow"`, and serde `flatten`, and is theoretically grounded by the W3C TAG must-ignore/must-understand model — so the RFC can cite well-established precedent. The sharpest open gap is **JSON-specific**: the ecosystems that get preservation "for free" (Protobuf) do so only in binary, while NGFF lives in JSON, so the backend must implement an *explicit* carrier and verify it survives the full round-trip (`attrs → typed model → zarr.json → reload`), including nested nodes and key ordering. A secondary item — whether `ome-zarr-models-py` actually configures `extra="allow"` everywhere — is a code-level verification, not a literature gap.

---

# Angle C — Coordinate transforms & multiscale representation

## TL;DR

- **xarray already ships the exact primitive for NGFF transforms:** `CoordinateTransform` / `CoordinateTransformIndex` ([PR #9543](https://github.com/pydata/xarray/pull/9543), released ~2025.01) back coordinates with a mathematical function (scale/translate/affine) instead of a materialized array — supporting label-based selection and lazy reprs. NGFF `scale`+`translation` per dataset is precisely an affine from array space to physical space, so each multiscale level maps to one `CoordinateTransformIndex` ([xarray.dev/blog](https://xarray.dev/blog/flexible-indexing)).
- **`rasterix.RasterIndex` is the closest working precedent:** it wraps a 2D affine via `CoordinateTransformIndex` and *correctly recomputes the affine under slicing/coarsening* (a `step:10` slice multiplies the scale by 10) — exactly what a pyramid level needs ([xarray-indexes docs](https://xarray-indexes.readthedocs.io/earth/raster.html)).
- **SpatialData and multiscale-spatial-image have already built NGFF-pyramid-on-DataTree:** each level is a DataTree node (`/scale0`, `/scale1`…) encoding the downsample scale+offset into per-level coordinate values (y → `0.5, 2.5, 4.5…` at 2×) ([multiscale-spatial-image](https://github.com/spatial-image/multiscale-spatial-image/blob/main/README.md)).
- **NGFF RFC-5 dramatically expands the transform model** beyond 0.4/0.5's per-dataset scale/translation: named `coordinateSystems`, a *fully-connected transformation graph*, affine, rotation, mapAxis, sequence, byDimension, displacement/coordinate fields. Any mapping must be forward-compatible with this graph, not just affine-per-level ([ngff.openmicroscopy.org/rfc/5](https://ngff.openmicroscopy.org/rfc/5/)).
- **GDAL/rasterio prove the affine-as-6-coefficients pattern is the geospatial standard** — but also the footgun: GDAL's `[c,a,b,f,d,e]` order differs from `affine.Affine`, and both being 6-tuples causes silent errors — a caution for NGFF's row/column-major affine storage ([GDAL](https://gdal.org/en/stable/tutorials/geotransforms_tut.html), [affine](https://github.com/rasterio/affine)).
- **DataTree fits pyramids natively, with one discipline:** alignment is checked only *vertically* (each node against its ancestors, `join="exact"`), never between siblings — so sibling levels of different sizes coexist freely. Each level just owns its spatial coords *locally*; the only footgun is putting a per-level spatial coord on a *shared ancestor*, which exact-join then rejects. Genuinely-shared axes (`c`, `t`) may live on the root and be inherited ([xarray #9077](https://github.com/pydata/xarray/issues/9077), [hierarchical-data docs](https://docs.xarray.dev/en/stable/user-guide/hierarchical-data.html)).
- **COG overviews are the imaging analog but carry no per-level transform metadata** — each overview is implicitly ½ resolution, so the transform is conventional, not stored. NGFF's explicit per-level `coordinateTransformations` is strictly richer ([cogeo.org](https://cogeo.org/in-depth.html)).
- **CF `grid_mapping` shows the "transform-as-sidecar-variable" alternative** — store the CRS/affine in a scalar variable referenced by attribute, vs. baking it into a `CoordinateTransformIndex`.

**Figure C-1 — Multiscales → DataTree, one node per level.** DataTree checks alignment only *vertically* (each node against its ancestors), so sibling levels of different sizes coexist freely — a pyramid is a natural fit. Each level owns a local `CoordinateTransformIndex` built from its own NGFF `scale`+`translation`; only genuinely-shared axes (channel `c`, time `t`) are inherited from the root. The single footgun: don't place a per-level spatial coord on a shared ancestor, or vertical exact-join alignment will reject the tree.

```{mermaid}
flowchart TB
    root["<b>/</b> (root)<br/>multiscales metadata<br/>inherited coords: c, t"]
    root --> s0["<b>/scale0</b> (full res)<br/>y,x → CoordinateTransformIndex<br/>scale₀, translation₀"]
    root --> s1["<b>/scale1</b> (½)<br/>y,x → CoordinateTransformIndex<br/>scale₁, translation₁"]
    root --> s2["<b>/scale2</b> (¼)<br/>y,x → CoordinateTransformIndex<br/>scale₂, translation₂"]
    note["RFC-5 forward-compat: a node may also<br/>carry named coordinateSystems +<br/>inter-element transforms (graph)"]
    s0 -.-> note
    style note fill:#eef,stroke:#88a,stroke-dasharray: 4 4
```

### A. Flexible coordinate transform (CoordinateTransform / CoordinateTransformIndex) (2024–2025)
**Links:** https://github.com/pydata/xarray/pull/9543 · https://docs.xarray.dev/en/stable/generated/xarray.indexes.CoordinateTransformIndex.html · https://xarray.dev/blog/flexible-indexing
**Author/Org:** Benoît Bovy / pydata (xarray)
**Year:** 2024–2025
**Summary:** Adds an abstract `CoordinateTransform` and a `CoordinateTransformIndex` wrapper letting third parties define coordinates by a forward/inverse function rather than a stored array. Creates lazy coordinate variables, supports point-wise label-based selection via the inverse, and aligns by comparing transforms. `RangeIndex` and `rasterix.RasterIndex` are built on it.
**Relevance to NGFF↔xarray:** The single most directly applicable primitive. NGFF's `scale`+`translation` is `X(i) = scale*i + translation` — exactly what `CoordinateTransform` expresses — giving lazy physical coords per pyramid level without materializing huge arrays, plus working `.sel()` in physical units.
**What it's missing / limitations:** Public API young/low-level; only point-wise selection (not interval); no built-in N-D affine helper beyond rasterix; no story for RFC-5's coordinate-system *graph*.
**Depth:** deep-technical
**Quality:** Authoritative — the primary upstream source, by xarray's index lead.

### B. rasterix RasterIndex — raster affine transforms (2024–2025)
**Links:** https://xarray-indexes.readthedocs.io/earth/raster.html
**Author/Org:** Deepak Cherian / xarray-contrib (rasterix)
**Year:** 2024–2025
**Summary:** Implements a `RasterIndex` storing a 2D affine and computing pixel-center coordinates lazily via `CoordinateTransformIndex`. Critically *updates the affine under slicing/striding* (a `[100:200:10]` slice multiplies pixel size by 10, shifts origin) and validates alignment on concatenation.
**Relevance to NGFF↔xarray:** The best end-to-end demonstration that affine-backed lazy coords survive the operations a pyramid needs. Each multiscale level is essentially a strided/scaled view of level 0; rasterix shows the affine recomputation mirroring NGFF per-level scale/translation — strongly suggesting each DataTree node holds its own RasterIndex-like affine.
**What it's missing / limitations:** 2D-raster-focused; NGFF needs ≥5D and three independent `space` axes; no pyramid orchestration (per-array, not per-tree).
**Depth:** deep-technical
**Quality:** High — concrete reference implementation of the target pattern.

### C. multiscale-spatial-image (2021–2024)
**Links:** https://github.com/spatial-image/multiscale-spatial-image/blob/main/README.md
**Author/Org:** spatial-image org (Matt McCormick et al.)
**Year:** 2021–2024
**Summary:** Generates a chunked multiscale pyramid as an xarray DataTree, one node per scale (`/scale0`, `/scale1`…), each a `spatial-image` Dataset, serializable to OME-NGFF. Per-level downsample scale and half-pixel offset are encoded directly into each level's coordinate values.
**Relevance to NGFF↔xarray:** The flagship prior art for "multiscales → DataTree, one node per level." Already demonstrates encoding NGFF scale/translation as physical coordinates per level and round-tripping to OME-NGFF. Materialized coords vs. lazy `CoordinateTransformIndex` is the key design decision left to make.
**What it's missing / limitations:** Coordinates appear materialized (predates `CoordinateTransformIndex`); light on how transform metadata round-trips and on RFC-5 forward-compat; uses `attrs`-stored transforms.
**Depth:** accessible
**Quality:** High — production library, direct precedent; light on internals docs.

### D. SpatialData design doc — coordinate systems & transformation graph (2023–2024)
**Links:** https://spatialdata.scverse.org/en/stable/design_doc.html · https://spatialdata.scverse.org/en/latest/tutorials/notebooks/notebooks/examples/transformations.html · https://github.com/scverse/spatialdata/issues/308
**Author/Org:** scverse / SpatialData (Marconato et al.)
**Year:** 2023–2024
**Summary:** Defines intrinsic vs. extrinsic coordinate systems, with transformations (`Identity`, `Scale`, `Translation`, `Affine`, `Sequence`, `MapAxis`) connecting them, and a graph so `get_transformation_between_coordinate_systems` finds a path via composition/inverses. Maintains two class hierarchies (NGFF-compliant `Ngff*` and self-contained `BaseTransformation`). Multiscale images use DataTree with transforms in `attrs`.
**Relevance to NGFF↔xarray:** The most mature *typed* transform model in the Python ecosystem, already pairing a transform graph with DataTree pyramids. Directly informs RFC-5 forward-compat: how to keep a clean in-memory transform object separate from NGFF serialization, and how to handle axis pass-through. A reference for the "no raw dicts, typed API" requirement.
**What it's missing / limitations:** Transforms live in `attrs`, not coordinates/indexes — so `.sel()` in physical units isn't transform-aware. Two parallel hierarchies add complexity; coupling to anndata/scverse assumptions.
**Depth:** deep-technical
**Quality:** Excellent — peer of this RFC's problem, with a shipped graph implementation.

### E. NGFF RFC-5: Coordinate Systems and Transformations (2024–2025)
**Links:** https://ngff.openmicroscopy.org/rfc/5/ · https://github.com/ome/ngff/pull/138 · https://github.com/ome/ngff/issues/84
**Author/Org:** John Bogovic et al. / OME (ome/ngff)
**Year:** 2024–2025 (versions through 2025-10-31)
**Summary:** Replaces bare per-dataset `coordinateTransformations` with named `coordinateSystems` and a *fully-connected transformation graph*. Adds identity, scale, translation, mapAxis, affine (a *homogeneous* matrix — the augmented M×(N+1) form that folds translation into a single matrix multiply; stored in JSON or as a Zarr array), rotation, sequence, byDimension, bijection, and field-based coordinates/displacements. Transforms reference `input`/`output` coordinate systems by name.
**Relevance to NGFF↔xarray:** Defines the *target* the mapping must not lose data against. Affine is first-class and may be stored as a Zarr array (so an affine can itself be an xarray variable). The graph + named systems mean a single DataTree may carry multiple coordinate systems and inter-element transforms — beyond simple per-level affine coords.
**What it's missing / limitations:** Still a draft (not in 0.5); implementations may pick a subset. No xarray-specific guidance. The *graph* model — named coordinate systems with inter-element cross-references — is harder to fit into a tree than a simple pyramid is (a tree expresses parent/child, not arbitrary cross-links).
**Depth:** spec
**Quality:** Authoritative — the normative future spec; primary source.

### F. GDAL geotransform + rasterio `affine` library (ongoing)
**Links:** https://gdal.org/en/stable/tutorials/geotransforms_tut.html · https://github.com/rasterio/affine · https://affine.readthedocs.io/
**Author/Org:** OSGeo/GDAL; rasterio org
**Year:** ongoing
**Summary:** GDAL's geotransform is the canonical 6-coefficient affine from (col,row) to projected (X,Y): `X = c + col*a + row*b`, `Y = f + col*d + row*e`. rasterio uses `affine.Affine` (3×3); `Affine.from_gdal()` converts, and the library raises rather than silently accept a GDAL-ordered tuple.
**Relevance to NGFF↔xarray:** The dominant real-world affine-as-coordinate model with a 25-year track record. The ordering footgun (GDAL `[c,a,b,f,d,e]` vs `affine.Affine` vs NGFF row/column-major) is a concrete warning for unambiguous parsing of NGFF affines.
**What it's missing / limitations:** 2D only; no pyramid concept; no time/channel axes; CRS handled outside the affine.
**Depth:** spec / deep-technical
**Quality:** Authoritative — battle-tested standard.

### G. Cloud-Optimized GeoTIFF overviews (ongoing)
**Links:** https://cogeo.org/in-depth.html · https://gdal.org/en/stable/drivers/raster/cog.html · https://github.com/cogeotiff/cog-spec/blob/master/spec.md
**Author/Org:** cogeo.org / OGC / GDAL
**Year:** ongoing (OGC standard 2023)
**Summary:** COGs embed lower-resolution overviews (each ~½ the previous) as additional IFDs, letting clients fetch coarse views without reading full resolution. An internal pyramid keyed by power-of-two reduction.
**Relevance to NGFF↔xarray:** The imaging precedent for pyramids, and an instructive contrast: COG overviews have *no explicit per-level transform metadata* — the ½ relationship is conventional. This is exactly the gap NGFF closes with explicit per-dataset `coordinateTransformations`, and why a DataTree-of-plain-arrays drops information unless transforms become coordinates/attrs per node.
**What it's missing / limitations:** Implicit power-of-two only; 2D; no arbitrary scale/translation per level; transform not machine-described.
**Depth:** spec
**Quality:** High — widely deployed standard; relevant mainly as contrast.

### H. xarray DataTree coordinate inheritance & alignment (2024)
**Links:** https://github.com/pydata/xarray/issues/9077 · https://docs.xarray.dev/en/stable/user-guide/hierarchical-data.html
**Author/Org:** Stephan Hoyer, Tom Nicholas / pydata
**Year:** 2024
**Summary:** Coordinates on a parent node are inherited by descendants, and each node must be exactly aligned with its *ancestors* on inherited dims/indexes — alignment is vertical only, so **siblings may differ freely**. A conflict arises only when a coordinate on a *shared ancestor* clashes with a descendant's dim; some valid multi-group Zarr/netCDF that put conflicting coords on a common parent cannot load into a single tree.
**Relevance to NGFF↔xarray:** Decisive constraint for "multiscales → DataTree." Because pyramid levels have different spatial dim lengths and values, spatial coords cannot be inherited from the root; each level defines its own (sharing only non-spatial coords like channel names). Confirms one-node-per-level is viable but forces local per-node spatial indexes — aligning with a per-node `CoordinateTransformIndex`.
**What it's missing / limitations:** Inheritance helps only for axes genuinely shared across levels (`c`, `t`); the downsampled spatial axes use the *non-inherited*, local path. The docs don't address multiscale imagery specifically.
**Depth:** deep-technical
**Quality:** Authoritative — core design issue by DataTree authors.

### I. CF Conventions grid_mapping & cf_xarray (ongoing)
**Links:** https://github.com/cf-convention/cf-conventions/blob/main/ch05.adoc · https://cf-xarray.readthedocs.io/en/latest/grid_mappings.html
**Author/Org:** CF Conventions community; xarray-contrib
**Year:** ongoing
**Summary:** CF encodes the CRS in a separate scalar "grid mapping" variable, referenced by a data variable's `grid_mapping` attribute; projected coordinates carry true lat/lon via the `coordinates` attribute or `crs_wkt`. rioxarray surfaces this as `.rio.crs`/`.rio.transform()`.
**Relevance to NGFF↔xarray:** Demonstrates the alternative "transform/CRS as sidecar variable + attribute pointer" vs. embedding the transform in an index. Useful for the trade-off discussion and shows precedent for representing an affine as a *variable* — dovetailing with RFC-5 allowing affines stored as Zarr arrays.
**What it's missing / limitations:** CRS-centric, not pyramid-aware; grid_mapping is descriptive, not an executable lazy transform for `.sel()`; verbose attribute conventions are dict-like (counter to "no raw dicts").
**Depth:** spec
**Quality:** High — mature standard; informs the attrs-vs-index choice.

## Gap verdict — Angle C
The two hard sub-problems are individually well-precedented but **not yet combined the way this RFC needs**: `CoordinateTransformIndex`/rasterix solve "affine → lazy coordinates with working physical-unit selection," and multiscale-spatial-image/SpatialData solve "NGFF pyramid → DataTree, one node per level" — but existing pyramid tools store materialized coords or `attrs` transforms rather than transform-backed indexes. (DataTree itself handles the pyramid fine — sibling levels with local coords; that part is solved.) The opportunity is to make each pyramid level a DataTree node whose spatial coordinates are a `CoordinateTransformIndex` built from that level's NGFF transform, while staying forward-compatible with RFC-5's multi-coordinate-system *graph* (which no DataTree-based tool currently models). Borrow SpatialData's typed transform hierarchy and rasterix's slice-aware affine recomputation.

---

# Angle D — Typed API design over loose dicts

## TL;DR

- **The xarray accessor pattern is the officially-sanctioned extension mechanism** — xarray recommends `register_*_accessor` *over subclassing* because accessors give an implicit namespace, avoid name conflicts, and don't break under "return a new object" semantics ([xarray docs](https://docs.xarray.dev/en/latest/internals/extending-xarray.html)). Directly validates the `.ngff` front-door.
- **"Parse, don't validate" (Alexis King, 2019) is the theoretical backbone for "no raw dicts":** parse loose input into a constrained type *once at the boundary* so downstream code never re-checks ([lexi-lambda](https://lexi-lambda.github.io/blog/2019/11/05/parse-don-t-validate/)).
- **"Make illegal states unrepresentable" (Yaron Minsky, 2010; Feldman 2016)** is "make wrong things hard" restated as a discipline ([Jane Street](https://blog.janestreet.com/effective-ml-revisited/), [functional-architecture.org](https://functional-architecture.org/make_illegal_states_unrepresentable/)).
- **Raw dicts/JSON-in-attrs are textbook "Primitive Obsession"** — a recognized smell whose remedy is Value Objects that encapsulate validity ([ploeh](https://blog.ploeh.dk/2011/05/25/DesignSmellPrimitiveObsession/), [DevIQ](https://deviq.com/code-smells/primitive-obsession-code-smell/)).
- **cf-xarray, rioxarray, pint-xarray, MetPy are direct exemplars** of a typed/semantic API over loose attrs — cf-xarray interprets CF attributes into a `.cf` namespace ([cf-xarray](https://github.com/xarray-contrib/cf-xarray)); MetPy's `.metpy` parses CF grid-mapping into typed coordinate/unit operations ([MetPy](https://unidata.github.io/MetPy/latest/api/generated/metpy.xarray.html)).
- **ome-zarr-models-py is the strongest domain-specific prior art:** Pydantic models giving validation + IDE completion, *deliberately decoupled from I/O* ("these models do not handle reading or writing data") — exactly the typed-model-separate-from-persistence split ([tutorial](https://ome-zarr-models-py.readthedocs.io/en/latest/tutorial/), [comparison #407](https://github.com/ome/ome-zarr-py/issues/407)).
- **Pydantic's `extra="allow"` is the concrete mechanism for "never loses data"** — unknown fields preserved rather than dropped ([Pydantic config](https://docs.pydantic.dev/latest/api/config/)).
- **Hexagonal / ports-and-adapters supplies the layering vocabulary:** keep the domain (typed NGFF model) framework- and persistence-agnostic; the Zarr store is a "driven adapter" behind a port; the accessor is the "driving" side ([Wikipedia](https://en.wikipedia.org/wiki/Hexagonal_architecture_(software))).

**Figure D-1 — The layered architecture (ports & adapters).** The `.ngff` accessor is a thin, stateless front door; the typed model is the persistence-agnostic domain core; the carrier and the Zarr backend are swappable adapters. No layer below the accessor knows about the others above it.

```{mermaid}
flowchart TB
    user(["User code"]) --> ome
    subgraph facade [Front door]
        ome[".ngff accessor<br/>(thin, stateless, discoverable)"]
    end
    subgraph domain [Domain core — persistence-agnostic]
        typed["Typed NGFF model<br/>parse-don't-validate · no raw dicts"]
        sel["Selection<br/>CoordinateTransformIndex / RangeIndex"]
    end
    subgraph adapters [Driven adapters — swappable]
        carrier["Raw-zarr.json carrier<br/>(unknown/future fields)"]
        backend["Custom Zarr backend<br/>(read + deep-merge write)"]
    end
    ome --> typed
    ome --> sel
    typed --> carrier
    typed --> backend
    carrier --> backend
    backend --> store[("OME-Zarr store")]
```

### A. Extending xarray using accessors (official docs) (2024)
**Links:** https://docs.xarray.dev/en/latest/internals/extending-xarray.html
**Author/Org:** xarray developers (pydata)
**Year:** current/2024
**Summary:** The authoritative rationale for the accessor pattern. xarray steers extenders away from subclassing (which "easily breaks" and returns plain xarray objects) toward `register_*_accessor` decorators, giving "an implicit namespace... separate from built-in xarray methods," conflict avoidance, and per-instance caching — but with a caveat that new objects from arithmetic/`ds[var]` get fresh accessors, so accessors should not hold mutable cross-operation state.
**Relevance to NGFF↔xarray:** The primary justification for `.ngff` as the public front door, and confirmation it should be a thin, stateless typed view — pushing typed model + persistence into separate layers (the caching caveat argues *against* stashing parsed state on the accessor).
**What it's missing / limitations:** Mechanism-focused; no opinion on validation, typed return values, or round-trip fidelity.
**Depth:** spec
**Quality:** Primary source, authoritative, concise.

### B. Parse, Don't Validate (2019)
**Links:** https://lexi-lambda.github.io/blog/2019/11/05/parse-don-t-validate/
**Author/Org:** Alexis King
**Year:** 2019
**Summary:** Argues the difference between parsing and validation "lies almost entirely in how information is preserved": a validator discards what it learned; a parser "produces more-structured output," encoding the guarantee in the type. Parse once at the boundary into types that make illegal states unrepresentable, eliminating "shotgun parsing" (the same validation scattered and repeated all over the codebase).
**Relevance to NGFF↔xarray:** The intellectual core of "no raw dicts." Reading NGFF JSON/attrs into typed models at the boundary is "parsing"; downstream xarray code trusts the types and never re-inspects raw dicts. Motivates a parse-at-load / serialize-at-write boundary in the persistence layer.
**What it's missing / limitations:** Haskell-flavored; doesn't address forward-compat with unknown fields (where pure "parse" loses data unless explicitly preserved — see Angle B).
**Depth:** deep-technical
**Quality:** Seminal, widely-cited; primary source.

### C. Make Illegal States Unrepresentable / Effective ML (2010, revisited)
**Links:** https://blog.janestreet.com/effective-ml-revisited/ · https://functional-architecture.org/make_illegal_states_unrepresentable/
**Author/Org:** Yaron Minsky (Jane Street); popularized by Richard Feldman (elm-conf 2016)
**Year:** 2010 (origin)
**Summary:** "Model data in such a way that nonsensical ('illegal') values are inexpressible." Resulting models are simpler — fewer cases to handle. Feldman reframed it as "design the type so the bug literally cannot be written."
**Relevance to NGFF↔xarray:** The "make wrong things hard" requirement stated as an established principle with a citable lineage. Supports modeling NGFF constructs (axis types, transforms, channel windows) as constrained types/enums rather than free strings/dicts.
**What it's missing / limitations:** A slogan, not a recipe; doesn't address Python's weaker type system or runtime-only enforcement (Pydantic fills the gap).
**Depth:** accessible
**Quality:** Foundational, canonical attribution.

### D. ome-zarr-models-py — typed Pydantic NGFF models (2024–2025)
**Links:** https://ome-zarr-models-py.readthedocs.io/en/latest/tutorial/ · https://github.com/ome/ome-zarr-py/issues/407
**Author/Org:** OME community (successor to pydantic-ome-ngff)
**Year:** 2024–2025
**Summary:** Pydantic models providing automatic validation, IDE completion, and discoverable typed properties (`.ome_attributes`, `.datasets`). Crucially, "these models do not handle reading or writing data" — metadata structure only, delegating array I/O to zarr-python. Offers both strict (`Image.from_zarr()`) and exploratory (`open_ome_zarr()`) entry points.
**Relevance to NGFF↔xarray:** The most direct domain prior art and a near-perfect template for "typed-model layer separate from persistence." A candidate to *be* the typed layer under `.ngff`. Note: verify whether models permit `extra` fields (forward-compat).
**What it's missing / limitations:** Not an xarray integration — no dims/coords mapping; metadata-only, so the xarray bridge is still unsolved by it.
**Depth:** spec
**Quality:** Active, zarr-v3-native, community-backed primary source.

### E. cf-xarray, rioxarray, pint-xarray, MetPy — accessor exemplars over loose attrs (current)
**Links:** https://github.com/xarray-contrib/cf-xarray · https://cf-xarray.readthedocs.io/en/latest/ · https://unidata.github.io/MetPy/latest/api/generated/metpy.xarray.html · https://corteva.github.io/rioxarray/stable/getting_started/crs_management.html
**Author/Org:** xarray-contrib, corteva, Unidata
**Year:** current
**Summary:** Four production accessors putting a typed/semantic API over loose attrs. cf-xarray's `.cf` interprets CF attributes (`standard_name`, `axis`, `positive`) so users write `.cf.mean("latitude")`. MetPy's `.metpy` parses CF grid-mapping and adds unit-/coordinate-aware operations. rioxarray loads CRS/transform/nodata into `.rio`.
**Relevance to NGFF↔xarray:** The most direct *precedents* for `.ngff` — each interprets a domain convention in `attrs` and exposes a discoverable, typed namespace without forcing users to touch raw dicts. cf-xarray's convention-interpretation model is the closest analog to mapping NGFF axis/transform metadata.
**What it's missing / limitations:** Most ultimately *read* from raw attr dicts at call time (interpret-on-access) rather than parsing into a persisted typed model at load — a weaker form of "parse, don't validate."
**Depth:** accessible / deep-technical (source)
**Quality:** Battle-tested ecosystem standards; strong precedent.

### F. Pydantic configuration: `extra`, JSON parsing, TypeAdapter (current)
**Links:** https://docs.pydantic.dev/latest/api/config/ · https://docs.pydantic.dev/latest/concepts/json/
**Author/Org:** Pydantic
**Year:** current (v2)
**Summary:** Documents `extra="allow"` (preserves unknown input fields on the instance) plus `model_validate_json()` as a parse-at-boundary entry point. Notably, Pydantic v2 *dropped* `extra="allow"` for dataclasses (only `ignore`/`forbid`), so field preservation requires `BaseModel`.
**Relevance to NGFF↔xarray:** The concrete mechanism reconciling "parse, don't validate" with "never loses data": parse into a `BaseModel` with `extra="allow"` so unknown future NGFF fields survive. The dataclass caveat is a concrete implementation warning.
**What it's missing / limitations:** Runtime-only validation; no compile-time guarantees. `extra="allow"` stores extras untyped — preservation, not modeling.
**Depth:** spec
**Quality:** Primary docs; the de-facto Python validation tool.

### G. Primitive Obsession & Value Objects (2011–)
**Links:** https://blog.ploeh.dk/2011/05/25/DesignSmellPrimitiveObsession/ · https://deviq.com/code-smells/primitive-obsession-code-smell/
**Author/Org:** Mark Seemann (ploeh); DevIQ
**Year:** 2011 onward
**Summary:** Names the smell of "overuse of primitive types to represent rich domain concepts," which "break[s] encapsulation by allowing invalid values" and scatters validation. Remedy: small immutable Value Objects encapsulating validity at construction.
**Relevance to NGFF↔xarray:** The diagnostic vocabulary for why `dict`/`str`-in-attrs is bad — NGFF axis-type, units, color/window are domain concepts smuggled as primitives. Motivates Value-Object-style typed wrappers (enums, constrained models) as the typed layer's building blocks.
**What it's missing / limitations:** General OOP framing; no Python/scientific-data specifics or serialization guidance.
**Depth:** accessible
**Quality:** Well-established refactoring literature; ploeh is a respected primary voice.

### H. Hexagonal Architecture (Ports & Adapters) + Repository pattern (2005–)
**Links:** https://en.wikipedia.org/wiki/Hexagonal_architecture_(software) · https://dnsbrnd.medium.com/ports-and-adapters-hexagonal-architecture-uses-the-repository-pattern-it-is-not-an-alternative-a037e17dbe9f
**Author/Org:** Alistair Cockburn (2005); Denis Brandi (clarifying article)
**Year:** 2005 onward
**Summary:** Isolates a framework-agnostic domain core behind "ports," with technology-specific "adapters" (e.g. a persistence/repository adapter) implementing them via dependency inversion. The domain must not carry ORM/serialization annotations; persistence is defined in terms of the domain, not vice-versa.
**Relevance to NGFF↔xarray:** The layering rationale for separating accessor (driving adapter / facade) from typed model (domain) from Zarr serialization (driven adapter). Argues the typed NGFF model should be Zarr-agnostic, with OME-Zarr I/O as a swappable adapter — reinforcing ome-zarr-models-py's "no I/O in the model."
**What it's missing / limitations:** Enterprise/Java-centric examples; can be over-engineering for a library; no scientific-data/xarray specifics.
**Depth:** accessible
**Quality:** Canonical architecture pattern; well-sourced secondary material.

## Gap verdict — Angle D
The prior art is mature and directly transferable: the theoretical case ("parse, don't validate," "make illegal states unrepresentable," primitive obsession), the architectural case (hexagonal separation of domain from persistence), and the domain-specific case (ome-zarr-models-py's I/O-decoupled models) all converge on exactly the RFC's layered design, and cf-xarray/MetPy prove the `.ngff` accessor front-door is idiomatic. The unfilled gap is the *seam*: no existing work combines a typed, forward-compatible NGFF model (with `extra="allow"`-style preservation) **with** the xarray dims/coords mapping behind a single accessor — every precedent solves the typed-metadata half (ome-zarr-models, no xarray bridge) or the accessor-over-attrs half (cf-xarray, interpreting raw attrs on access). The RFC's contribution is precisely that synthesis.

---

# Library inventory — what our Zotero library already holds

_Note: the Zotero semantic-search backend was unavailable in this environment (`chromadb` missing); findings are keyword/collection-based, so coverage is title/abstract-level._

## TL;DR
- **Both canonical OME-NGFF/OME-Zarr papers are present** (Moore et al. 2021 *Nat Methods*; Moore et al. 2023 *Histochem Cell Biol*) — primary spec-context citations, motivating the format around a *common metadata model* for FAIR data.
- **The foundational xarray paper (Hoyer & Hamman 2017) is present** — the "N-D labeled arrays" target model is directly citable.
- **A strong "Zarr-as-substrate-for-rich-metadata" cluster from adjacent domains** — SpatialData, anndata, CZ CELLxGENE, VCF-Zarr, a spatial-transcriptomics standard — excellent prior art for *mapping a rich domain model onto a generic array/Zarr store* and *community data-model standardization*.
- **SpatialData (Marconato et al. 2024) is the single best analogue** for angles A, C, and D.
- **Solid generic array-storage literature is present** (Rusu 2023 survey; TileDB; CuTe layout algebra), but **the library has essentially nothing on CF conventions or netCDF** — Angle C is covered only indirectly, so external sources are needed there.

| Item (Zotero key) | Year | Best angle | Why it matters |
|---|---|---|---|
| OME-NGFF, Moore et al. — `B6JJ8PX3`, [doi](https://doi.org/10.1038/s41592-021-01326-w) | 2021 | A, B | Originating proposal paper; common-metadata-model + FAIR motivation |
| OME-Zarr community update, Moore et al. — `B8BB7GKD` | 2023 | A, B | Format maturity + ecosystem; standard, not single-lab |
| xarray, Hoyer & Hamman — `BC4CGQDM`, [doi](https://doi.org/10.5334/jors.148) | 2017 | A, D | Canonical citation for the *target* data model |
| SpatialData, Marconato et al. — `59UTBE5Z`, [doi](https://doi.org/10.1038/s41592-024-02212-x) | 2024 | A, C, D | Closest design analogue; transforms + common coordinate systems on NGFF/Zarr |
| anndata, Virshup et al. — `NRPMR8PG`, [doi](https://doi.org/10.21105/joss.04371) | 2024 | A, D | Array + dimension-aligned typed annotations; contrast to xarray coords |
| Spatial-transcriptomics standard, Jackson & Pachter — `BN5QE3IV`, [doi](https://doi.org/10.1016/j.xgen.2023.100374) | 2023 | B | "Why standardize" / community convergence framing |
| CZ CELLxGENE Discover — `UQ2JJ3GW` | 2024 | B, D | Enforced metadata schema enabling ecosystem-scale reuse |
| VCF-Zarr at Biobank scale, Czech et al. — `CU66NMPV`, [doi](https://doi.org/10.1093/gigascience/giaf049) | 2025 | A, B | Cross-domain analogue: encode a rich legacy model as Zarr, round-trip with existing tools |
| Multidimensional Array Data Management, Rusu — `DB9A2TEJ` | 2023 | A, D | Array-model survey; storage/typing design space |
| TileDB, Papadopoulos et al. — `WUJJA2VT` | 2016 | A | Storage-engine trade-offs; contrast to Zarr chunking (peripheral) |

**Lower-relevance items present:** napari (`84DP2QPE`, viewer/ecosystem citation), PetaKit5D (`A3KBPRN6`, scalability motivation), acquire-zarr (`37DAUMG4`, streaming acquisition), Zarr v3 core spec (`RH9JHK6W`, storage-layer citation), CuTe Layout Algebra (`7RTIU9TY`, low-level GPU layout — tangential), Onion Curve / space-filling curves (`CNLH9NRS`, peripheral).

**Honest gaps in the library:** no dedicated netCDF or CF-conventions paper; nothing on coordinate-transformation formalisms or typed-schema/pydantic validation. Angles C and D need the external sources cited above.

---

# Consolidated verdict: what the RFC must contribute

Prior art settles the *vocabulary and the primitives*; it does not settle the *synthesis*. Concretely, the RFC's defensible, novel contributions are:

1. **The seam.** A typed, forward-compatible NGFF model (`ome-zarr-models-py`-style, with `extra="allow"` verified throughout) *fused with* the xarray dims/coords mapping behind one `.ngff` accessor — the half no precedent has joined.
2. **A JSON carrier proven through the full round-trip.** Not Protobuf's free binary preservation, but an explicit `attrs → typed model → zarr.json → reload` carrier, tested on nested nodes and key ordering, to actually deliver "never lose data." (W3C must-ignore is the theory; the JSON implementation is ours.)
3. **NGFF's three hard features in one coherent model:** multiscale pyramids as a one-node-per-level DataTree (respecting strict-alignment inheritance by keeping spatial coords local), each level's spatial coordinates backed by a `CoordinateTransformIndex` (rasterix-style, slice-aware), and omero/channel metadata typed — all forward-compatible with RFC-5's coordinate-system *graph*, which no DataTree tool currently models.

**Immediate, code-level follow-ups flagged by the research (not literature gaps):**
- Verify `ome-zarr-models-py` sets `extra="allow"` on every model node; if any default to `ignore`/`forbid`, the lossless requirement fails silently.
- Decide materialized coords vs. `CoordinateTransformIndex`-backed coords per pyramid level (multiscale-spatial-image does the former; rasterix proves the latter).
- Pin down unambiguous affine ordering (the GDAL/`affine` footgun) before parsing NGFF affines.

---

## Glossary

The patterns and terms this survey leans on, in plain language. (Hover any {term}`carrier / passthrough pattern`-style link above to see its definition inline.)

:::{glossary}
impedance mismatch
: Borrowed from electrical engineering — the friction that arises when a rich, opinionated domain model (NGFF) doesn't line up cleanly with the more generic container (xarray/Zarr) it has to fit into. Most of this survey is about managing that friction.

carrier / passthrough pattern
: A technique for *not losing data* when you parse structured metadata into typed objects. You model the fields you understand, and keep a **verbatim** copy of everything you don't — unknown or future-spec fields — so you can write it back unchanged. The mental image: re-saving a Zarr group's `attrs` *including* the keys your reader didn't recognise, instead of silently dropping them.

forward-compatibility
: The property that an **older** reader can open a file written against a **newer** version of a spec without discarding the parts it doesn't yet understand. The carrier pattern is how you get it.

must-ignore / must-understand
: A rule from protocol/spec design. A reader must *ignore but preserve* fields it doesn't recognise (so the file round-trips intact) — **unless** a field is explicitly flagged *must-understand*, in which case the reader should refuse the file rather than silently misinterpret it.

parse, don't validate
: Convert loose input (a raw dict or JSON blob) into a typed object **once**, at the system boundary, so the rest of the code can trust the type instead of re-checking raw dictionaries everywhere. Coined by Alexis King (2019).

make illegal states unrepresentable
: Design your types so a nonsensical value simply **cannot be constructed** — e.g. an axis with no name, or an intensity window with `min > max`, becomes impossible to build rather than something you remember to check for at runtime.

ports and adapters
: Also called *hexagonal architecture*. A layering style that keeps the core data model independent of how it is stored or displayed: reading and writing OME-Zarr becomes a swappable "adapter" plugged into the model, not logic baked into the model itself.
:::

## Sources index (primary)

**Specs & standards:** NGFF 0.5 + RFC-5 (ngff.openmicroscopy.org/rfc/5), Zarr v3 core, OME-NGFF papers (Moore 2021/2023), CF Conventions (ch05 grid_mapping), GeoZarr CHARTER, COG/OGC spec, STAC datacube/xarray-assets, OpenAPI 3.1, JSON Schema, Avro 1.11, Protocol Buffers, SOAP 1.2, W3C TAG versioning, IETF draft-iab-protocol-maintenance.
**xarray internals:** accessors docs, CoordinateTransform/CoordinateTransformIndex (PR #9543), DataTree inheritance (#9077), hierarchical-data user guide, flexible-indexing blog.
**Libraries:** ome-zarr-models-py, SpatialData (+ design doc), multiscale-spatial-image, rasterix, cf-xarray, rioxarray, MetPy, pint-xarray, bioio/AICSImageIO, ome-zarr-py, Pydantic, serde, ruamel.yaml, tomlkit, GDAL/affine.
**Theory:** Hoyer & Hamman 2017 (xarray), Unidata CDM, "Parse, don't validate" (King 2019), "Make illegal states unrepresentable" (Minsky 2010 / Feldman 2016), Primitive Obsession (Seemann), Hexagonal Architecture (Cockburn 2005), Robustness Principle Reconsidered (Allman 2011), W3C TAG versioning (Orchard 2006).
**Cross-domain analogues (Zotero):** VCF-Zarr (Czech 2025), anndata (Virshup 2024), CZ CELLxGENE (2024), spatial-transcriptomics standard (Jackson & Pachter 2023), array-management survey (Rusu 2023), TileDB (2016).
