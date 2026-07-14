# NGFF 0.5 Specification (Local Copy)

```{note}
This is a local copy of the [NGFF 0.5 specification](https://ngff.openmicroscopy.org/0.5/)
for cross-referencing within this research book. Last fetched: 2026-02-24.

The spec is published by the Open Microscopy Environment consortium. We use "NGFF" to refer
to the format/spec and "OME-Zarr" when referring to concrete `.ome.zarr` stores.
```

## Abstract

This document contains next-generation file format (NGFF) specifications for storing bioimaging data in the cloud. All specifications are submitted to the https://image.sc community for review.

## Document conventions

The key words 'MUST', 'MUST NOT', 'REQUIRED', 'SHALL', 'SHALL NOT', 'SHOULD', 'SHOULD NOT', 'RECOMMENDED', 'MAY', and 'OPTIONAL' are to be interpreted as described in RFC 2119.

## 1. Storage format

OME-Zarr is implemented using the Zarr format as defined by version 3 of the Zarr specification. All features of the Zarr format including codecs, chunk grids, chunk key encodings, data types and storage transformers may be used with OME-Zarr unless explicitly disallowed in this specification.

### 1.1. Images

The following layout describes the expected Zarr hierarchy for images with multiple levels of resolutions and optionally associated labels. Note that the number of dimensions is variable between 2 and 5 and that axis names are arbitrary, see {ref}`multiscales-metadata` for details.

```text
├── 456.zarr                  # An OME-Zarr image
│   ├── zarr.json             # Group-level attributes include "multiscales" and "omero"
│   ├── 0                     # Each multiscale level is a separate Zarr array
│   │   ├── zarr.json         # All image arrays must be up to 5-dimensional
│   │   └─ ...                # Chunks stored per Zarr array spec
│   ├── n
│   └── labels
│       ├── zarr.json         # Contains list of labels: { "labels": [ "original/0" ] }
│       └── original
│           └── 0             # Multiscale labeled image
│               ├── zarr.json # Both multiscaled image and labeled image metadata
│               ├── 0
│               └── ...
```

### 1.2. High-content screening

Three groups MUST be defined above the images:

- the **well** group (implements well spec) — all images in a well are fields of view
- the **row** group above the well
- the **plate** group (implements plate spec) — a 2D collection of wells in rows and columns

```text
└── 5966.zarr                 # One OME-Zarr plate
    ├── zarr.json             # Implements "plate" specification
    ├── A                     # Row
    │   ├── 1                 # Column
    │   │   ├── zarr.json     # Implements "well" specification
    │   │   ├── 0             # Field of view (implements "multiscales", "omero")
    │   │   │   ├── zarr.json
    │   │   │   ├── 0         # Resolution levels
    │   │   │   └── labels    # Labels (optional)
    │   │   └── ...
    │   └── ...
    └── ...
```

## 2. OME-Zarr Metadata

OME-Zarr Metadata is stored in `zarr.json` files under the namespaced key `ome` in `attributes`. The version is denoted as a string in the `version` attribute within the `ome` namespace.

The OME-Zarr Metadata version MUST be consistent within a hierarchy.

```json
{
  "attributes": {
    "ome": {
      "version": "0.5"
    }
  }
}
```

(axes-metadata)=
### 2.1. "axes" metadata

"axes" describes the dimensions of a physical coordinate space. It is a list of dictionaries, where each dictionary describes a dimension (axis) and:

- **MUST** contain the field `"name"` that gives the name for this dimension. The values MUST be unique across all "name" fields.
- **SHOULD** contain the field `"type"`. It SHOULD be one of `"space"`, `"time"` or `"channel"`, but MAY take other string values for custom axis types.
- **SHOULD** contain the field `"unit"` to specify the physical unit of this dimension. The value SHOULD be one of the following strings (valid units per UDUNITS-2):

**Units for "space" axes:** angstrom, attometer, centimeter, decimeter, exameter, femtometer, foot, gigameter, hectometer, inch, kilometer, megameter, meter, micrometer, mile, millimeter, nanometer, parsec, petameter, picometer, terameter, yard, yoctometer, yottameter, zeptometer, zettameter

**Units for "time" axes:** attosecond, centisecond, day, decisecond, exasecond, femtosecond, gigasecond, hectosecond, hour, kilosecond, megasecond, microsecond, millisecond, minute, nanosecond, petasecond, picosecond, second, terasecond, yoctosecond, yottasecond, zeptosecond, zettasecond

The length of "axes" MUST be equal to the number of dimensions of the arrays that contain the image data.

The `"dimension_names"` attribute MUST be included in the `zarr.json` of the Zarr array of a multiscale level and MUST match the names in the "axes" metadata.

(coordinate-transformations-metadata)=
### 2.2. "coordinateTransformations" metadata

"coordinateTransformations" describe a series of transformations that map between two coordinate spaces (defined by "axes"). For example, to map a discrete data space of an array to the corresponding physical space. It is a list of dictionaries. Each entry describes a single transformation and MUST contain the field `"type"`.

| type | fields | description |
|------|--------|-------------|
| `identity` | | identity transformation, is the default |
| `translation` | one of: `"translation":List[float]`, `"path":str` | translation vector, stored as a list of floats or as binary data at a path in this container |
| `scale` | one of: `"scale":List[float]`, `"path":str` | scale vector, stored as a list of floats or as binary data at a path in this container |

The transformations in the list are applied sequentially and in order.

(multiscales-metadata)=
### 2.3. "multiscales" metadata

Metadata about an image can be found under the `"multiscales"` key in the group-level OME-Zarr Metadata. It is stored in a multiple resolution representation.

"multiscales" contains a list of dictionaries where each entry describes a multiscale image.

Each "multiscales" dictionary:

- **MUST** contain the field `"axes"`, see {ref}`axes-metadata`. The length of "axes" must be between 2 and 5 and MUST equal the dimensionality of the zarr arrays. The "axes" MUST contain 2 or 3 entries of `"type:space"` and MAY contain one `"type:time"` and MAY contain one `"type:channel"` or null/custom type. The entries MUST be ordered by "type": time first (if present), then channel/custom (if present), then space. For 3 spatial axes with anisotropic stacking, the order SHOULD be `"zyx"`.

- **MUST** contain the field `"datasets"`, a list of dictionaries describing arrays for individual resolution levels. Each dictionary:
  - **MUST** contain `"path"` — path to the array relative to the current zarr group. Paths MUST be ordered from largest (highest resolution) to smallest.
  - **MUST** contain `"coordinateTransformations"` — transformations mapping data coordinates to physical coordinates (per {ref}`coordinate-transformations-metadata`). The transformation MUST only be `translation` or `scale`. They MUST contain exactly one `scale` specifying pixel size in physical units. If scaling info is not available for an axis, the value MUST express the scaling factor between the current resolution and the first resolution, defaulting to 1.0. MAY contain exactly one `translation` specifying offset from origin. If `translation` is given it MUST be listed after `scale`. The length of `scale` and `translation` MUST equal the length of "axes".

- **MAY** contain the field `"coordinateTransformations"` — transformations applied to all resolution levels (applied after per-dataset transforms). Same rules as dataset-level transforms.

- **SHOULD** contain the field `"name"`.

- **SHOULD** contain the field `"type"` (downscaling method) and `"metadata"` (additional info about the method).

#### Example

```json
{
  "zarr_format": 3,
  "node_type": "group",
  "attributes": {
    "ome": {
      "version": "0.5",
      "multiscales": [
        {
          "name": "example",
          "axes": [
            { "name": "t", "type": "time", "unit": "millisecond" },
            { "name": "c", "type": "channel" },
            { "name": "z", "type": "space", "unit": "micrometer" },
            { "name": "y", "type": "space", "unit": "micrometer" },
            { "name": "x", "type": "space", "unit": "micrometer" }
          ],
          "datasets": [
            {
              "path": "0",
              "coordinateTransformations": [
                { "type": "scale", "scale": [1.0, 1.0, 0.5, 0.5, 0.5] }
              ]
            },
            {
              "path": "1",
              "coordinateTransformations": [
                { "type": "scale", "scale": [1.0, 1.0, 1.0, 1.0, 1.0] }
              ]
            },
            {
              "path": "2",
              "coordinateTransformations": [
                { "type": "scale", "scale": [1.0, 1.0, 2.0, 2.0, 2.0] }
              ]
            }
          ],
          "coordinateTransformations": [
            { "type": "scale", "scale": [0.1, 1.0, 1.0, 1.0, 1.0] }
          ],
          "type": "gaussian",
          "metadata": {
            "method": "skimage.transform.pyramid_gaussian",
            "version": "0.16.1",
            "args": "[true]",
            "kwargs": { "multichannel": true }
          }
        }
      ]
    }
  }
}
```

(omero-metadata)=
### 2.4. "omero" metadata (transitional)

Transitional information specific to the channels of an image and how to render it can be found under the `"omero"` key in the group-level metadata.

```json
{
  "id": 1,
  "name": "example.tif",
  "channels": [
    {
      "active": true,
      "coefficient": 1,
      "color": "0000FF",
      "family": "linear",
      "inverted": false,
      "label": "LaminB1",
      "window": {
        "end": 1500,
        "max": 65535,
        "min": 0,
        "start": 0
      }
    }
  ],
  "rdefs": {
    "defaultT": 0,
    "defaultZ": 118,
    "model": "color"
  }
}
```

The "omero" metadata is optional, but if present:
- **MUST** contain the field `"channels"`, an array of dictionaries describing the channels.
- Each channel **MUST** contain `"color"` — a string of 6 hex digits (RGB).
- Each channel **MUST** contain `"window"` — a dictionary with fields `"min"`, `"max"`, `"start"`, and `"end"`.

(labels-metadata)=
### 2.5. "labels" metadata

Zarr arrays representing pixel-annotation data are stored in a `"labels"` group nested within an image group. Label images MUST be integer data types (`uint8`, `int8`, `uint16`, `int16`, `uint32`, `int32`, `uint64`, `int64`).

The OME-Zarr Metadata for the "labels" group MUST contain a `labels` key whose value is a JSON array of paths to labeled multiscale images:

```json
{
  "attributes": {
    "ome": {
      "version": "0.5",
      "labels": ["cell_space_segmentation"]
    }
  }
}
```

The label image `zarr.json` MUST implement multiscales and SHOULD contain an `"image-label"` key with:
- `"colors"` — array with `"label-value"` (integer) and optional `"rgba"` (array of 4 uint8 values)
- `"properties"` — array with `"label-value"` and arbitrary key-value metadata per label
- `"source"` — object with optional `"image"` path (default `"../../"`)

#### Example

```json
{
  "attributes": {
    "ome": {
      "version": "0.5",
      "image-label": {
        "colors": [
          { "label-value": 0, "rgba": [0, 0, 128, 128] },
          { "label-value": 1, "rgba": [0, 128, 0, 128] }
        ],
        "properties": [
          { "label-value": 0, "area (pixels)": 1200, "class": "intercellular space" },
          { "label-value": 1, "area (pixels)": 1650, "class": "cell", "cell type": "neuron" }
        ],
        "source": { "image": "../../" }
      }
    }
  }
}
```

(plate-metadata)=
### 2.6. "plate" metadata

The `plate` dictionary:
- **MUST** contain `"columns"` — list of objects with `"name"` (alphanumeric, unique, case-sensitive)
- **MUST** contain `"rows"` — list of objects with `"name"` (alphanumeric, unique, case-sensitive)
- **MUST** contain `"wells"` — list of objects with `"path"` (row name + `/` + column name), `"rowIndex"`, `"columnIndex"` (0-based)
- **MUST** contain `"version"`
- **SHOULD** contain `"name"`, `"field_count"`
- **MAY** contain `"acquisitions"` — list of objects with `"id"` (unique integer ≥ 0), optional `"name"`, `"maximumfieldcount"`, `"description"`, `"starttime"`, `"endtime"`

(well-metadata)=
### 2.7. "well" metadata

The `well` dictionary:
- **MUST** contain `"images"` — list of objects with `"path"` (alphanumeric, unique) and optional `"acquisition"` (integer matching a plate acquisition id)
- **SHOULD** contain `"version"`

## 3. Specification naming style

Multi-word keys in this specification should use the `camelCase` style.

## Version History

| Revision | Date | Description |
|----------|------|-------------|
| 0.5.2 | 2025-01-10 | Clarify that `dimension_names` MUST be included |
| 0.5.1 | 2025-01-10 | Re-add improved omero description |
| 0.5.0 | 2024-11-21 | Use Zarr v3 in OME-Zarr (RFC-2) |
| 0.4.0 | 2022-02-08 | Add axes type, units and coordinateTransformations |
| 0.3.0 | 2021-08-24 | Add axes field to multiscale metadata |
