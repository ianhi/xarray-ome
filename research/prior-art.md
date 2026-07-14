---
title: Prior Art — Microscopy Readers and xarray
---

# Prior Art: Microscopy Readers and xarray

This proposal learns from the microscopy-in-xarray ecosystem. This appendix surveys the existing tools — both OME-Zarr-native and broader microscopy readers — noting which conventions are de-facto standards and which are gaps the mapping improves on, and extracts the lessons that shaped the design.

## OME-Zarr-native tools

### ngff-zarr

[ngff-zarr](https://github.com/thewtex/ngff-zarr) is the reference parser for NGFF. It returns `NgffImage` dataclasses wrapping Dask arrays, with axes as `list[Axis]` and transforms as `ScaleTransform` / `TranslationTransform` objects. **No native xarray integration** — users must convert manually. Multiscales come back as a list of `NgffImage`, one per level.

*Lesson:* ngff-zarr is the clean "spec parser" layer. It makes no claim about data model. That separation is healthy — xarray-ngff should build on ngff-zarr rather than re-parsing NGFF.

### ome-zarr-py

[ome-zarr-py](https://github.com/ome/ome-zarr-py) is the OME reference reader. It returns a Node tree of Zarr arrays; metadata is parsed but not structured, multiscales are a flat list, and transforms live in raw JSON. **No xarray output.** The deliberate choice (see [issue #407](https://github.com/ome/ome-zarr-py/issues/407)) is to stay low-level.

*Lesson:* Another clean layering precedent — a reader library does not need to own the data model.

### pydantic-ome-ngff

[pydantic-ome-ngff](https://github.com/JaneliaSciComp/pydantic-ome-ngff) provides typed Pydantic models for NGFF metadata. **Zarr v2 only**, now superseded by [ome-zarr-models-py](https://github.com/ome-zarr-models/ome-zarr-models-py).

*Lesson:* Typed schemas help with validation but don't solve the representation problem on their own.

### spatialdata

[spatialdata](https://github.com/scverse/spatialdata) is the most ambitious production consumer of OME-Zarr-style data. It uses xarray's DataTree under the hood and layers custom `NgffCoordinateSystem` and transform classes on top (Identity, Scale, Translation, Affine, Sequence). Coordinates are materialized per spec; the writer includes explicit floating-point corrections to recover the original scale/translation from materialized coordinates.

*Lesson:* Spatialdata has already hit the hard problem — NGFF describes coordinates with 3 parameters (scale, translation, identity), xarray stores N materialized values, and round-tripping requires care. Our approach of stashing the original transform in attrs sidesteps this, at a memory cost we should quantify.

### multiscale-spatial-image

[multiscale-spatial-image](https://github.com/spatial-image/multiscale-spatial-image) generates multiscale pyramids as DataTree of xarray Datasets, serializable to NGFF. Write-focused; treats each level as a Dataset in a DataTree child — the same structural choice our mapping proposes.

## Multi-format microscopy readers

### bioio / aicsimageio

[bioio](https://github.com/bioio-devs/bioio) (successor to [aicsimageio](https://github.com/AllenCellModeling/aicsimageio)) is the dominant Python interface for producing xarray from microscopy files. It defines the de-facto convention:

- **`TCZYX`** fixed 5D ordering (Time, Channel, Z, Y, X)
- **`.xarray_data`** and **`.xarray_dask_data`** properties
- **Channel names** as string coords on `c`
- **Physical pixel sizes** as floats on `.physical_pixel_sizes` — *not* attached as coord attrs, and units are implicit
- **Scenes** via `.set_scene()`; each scene is a separate DataArray, never aggregated
- **Format-specific metadata** in `.metadata()`, not in xarray `attrs`

Format plugins (`bioio-czi`, `bioio-nd2`, `bioio-lif`, `bioio-ome-tiff`, `bioio-ome-zarr`) all conform to the same TCZYX output convention regardless of source.

#### Seen concretely: a real OME-Zarr 0.5 store

bioio is an excellent, widely-used package — but because it normalises *every* format to one fixed shape, it cannot honour what an OME-Zarr store actually says about itself. Take a public NGFF 0.5 image (IDR `idr0066`, a chicken-embryo MIP). Its `zarr.json` declares a **2-D** image with axes `y, x`, `unit: micrometer`, a finest-level `scale` of `1.6` µm/px, and an omero channel labelled `"Cy3"`.

Loading it with bioio:

```python
from bioio import BioImage
# note: the trailing slash must be absent
img = BioImage("https://livingobjects.ebi.ac.uk/idr/zarr/v0.5/idr0066/ExpD_chicken_embryo_MIP.ome.zarr")
img.dims    # <Dimensions [T: 1, C: 1, Z: 1, Y: 8978, X: 6510]>
img.shape   # (1, 1, 1, 8978, 6510)
img.xarray_dask_data
```

```text
<xarray.DataArray (T: 1, C: 1, Z: 1, Y: 8978, X: 6510)>
dask.array<..., chunksize=(1, 1, 1, 256, 256), dtype=uint8>
Coordinates:
  * C        (C) <U11 'Channel:/:0'
Dimensions without coordinates: T, Z, Y, X
Attributes:
    unprocessed:  GroupMetadata(attributes={'ome': {...}})   # opaque blob
```

Three faithful facts are lost in the trip:

- **The dimensionality is invented.** A 2-D `(y, x)` image becomes 5-D `(T, C, Z, Y, X)` with three size-1 axes that the store never declared.
- **The physical calibration vanishes.** `Y` and `X` carry *no coordinates* — the `1.6` µm scale and `micrometer` unit are dropped, so `sel(y=100.0)` in microns is impossible.
- **The channel identity is fabricated.** The one coordinate, `C`, is the placeholder `'Channel:/:0'`, not the omero label `"Cy3"`.

The original metadata is not *destroyed* — it sits in `attrs['unprocessed']` as a bioio `GroupMetadata` object — but it is an opaque passthrough, not a usable, typed representation.

The same store through this proposal's reference implementation keeps every fact:

```python
import xarray_ngff
ds = xarray_ngff.open_ngff_dataset(url)
ds.sizes             # {'y': 8978, 'x': 6510}          — verbatim, no invented axes
ds['y'].values[:3]   # array([0. , 1.6, 3.2])          — physical microns (TransformIndex-backed)
ds['y'].attrs        # {'units': 'micrometer', 'axis_type': 'space'}
ds.ngff.calibrated   # {'y': True, 'x': True}
ds.ngff.channels     # [Channel(label='Cy3', ...)]     — the real omero label
```

*Lesson:* the failure is not bioio's craftsmanship — it is what any *general-purpose, all-formats* reader must do: flatten to a lowest common denominator (fixed TCZYX, no units, format metadata parked to the side). An OME-Zarr-*native* mapping can instead honour the store's own axes, calibration, and channel metadata — which is exactly the gap this RFC closes (and the basis for the bioio → xarray-ngff adapter sketched in the reference implementation).

### nd2 (tlambert03)

[nd2](https://github.com/tlambert03/nd2) has a `.to_xarray()` method that **preserves the original axis order from the ND2 file** rather than forcing TCZYX. It attaches coordinate values derived from file metadata.

*Lesson:* An explicit counter-example to "TCZYX is the only way." A format-faithful philosophy is viable, and NGFF — where axes are self-describing — suits it well.

### Format-specific readers (no xarray)

| Reader | Format | Output |
|---|---|---|
| `pylibczirw`, `aicspylibczi`, `czifile` | CZI | numpy / dict |
| `tifffile` | TIFF / OME-TIFF | numpy, `aszarr()` |
| `ome-types` | OME-XML | typed dataclasses (schema only) |
| `readlif`, `liffile` | LIF | numpy |
| `nd2reader` | ND2 | numpy via PIMS |
| `imageio`, `scikit-image` | generic | numpy |

These reach xarray only via bioio plugins. CZI in particular has no direct CZI→xarray path.

### napari

Not a reader, but the main visualization target. Napari consumes `xarray.DataArray` directly and exposes `.axis_labels` and `.metadata` on image layers. Anything we put in `attrs` should remain displayable there; anything we put in coord attrs should survive slicing.

## What the ecosystem has settled on

Three conventions are effectively standardized:

1. **`TCZYX` dim ordering** — universal when xarray is produced from microscopy.
2. **Channel names as string coords on `c`** — enables `.sel(c="DAPI")`, used by every xarray-producing tool.
3. **Multiscales as DataTree** — spatialdata and multiscale-spatial-image both converged here.

Three conventions are **not** settled — and are where an NGFF-specific mapping can add real value:

1. **Units and axis types on coords.** Bioio drops them; spatialdata carries them internally but not in standardized xarray locations. NGFF has them in the spec, so the mapping surfaces them — the *where* is resolved in favour of CF-style coordinate attrs (see [](spec/axes.ipynb)).
2. **Multi-scene vs. multi-scale.** Bioio separates scenes with `.set_scene()`; NGFF multiscales are resolution pyramids, not scenes. DataTree is a natural fit for the pyramid; scene handling is out of scope here (NGFF 0.5 does not cover it).
3. **Lossless metadata round-trip.** Almost no tool does this. Bioio flattens to `.metadata()`, spatialdata reconstructs through its custom writer. Our design requirement 3 ("never loses data") makes this non-negotiable — the standard approach is to preserve the full NGFF metadata dict in `attrs` alongside the structured representation.

## Design implications

Our mapping can confidently:

- Use `TCZYX`-compatible axis-name → dim (adopted)
- Use string coords for channel labels (adopted)
- Use DataTree for multiscales (adopted)

It **improves on prior art** by:

- Attaching NGFF axis `type` and `unit` to coordinates in a discoverable way (resolved in favour of CF-style coordinate attrs; see the [axes page](spec/axes.ipynb))
- Guaranteeing lossless round-trip via full-metadata-dict preservation in `attrs` — a documented contract, not an implementation detail
- Using custom indexes ([`RangeIndex`](indexes/range-index.md), [`CoordinateTransformIndex`](indexes/coordinate-transform-index.md)) to represent NGFF transforms without eagerly materializing all coordinate values — a step beyond what spatialdata currently does

:::{seealso}
- [](spec/axes.ipynb) — how axes map to dims and where axis metadata lives
- [](mapping/transforms-to-coords.md) — scale/translation → coords or indexes
- [](mapping/multiscales-to-datatree.md) — the DataTree hierarchy choice
:::
