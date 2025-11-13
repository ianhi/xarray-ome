# OME-NGFF to xarray Mapping

This page documents how each component of the OME-NGFF metadata specification is mapped to xarray data structures.

## Design Philosophy

**Core Principle**: Metadata that can be represented in xarray's native data model (coordinates, dimension names) is stored there, not duplicated in attrs.

- **xarray coordinates**: Represent actual data (physical positions, channel labels)
- **xarray dimensions**: Represent axis names
- **xarray attrs**: Store metadata that has no native xarray representation

This design ensures:

- Natural xarray workflows (`.sel()`, `.isel()`, coordinate-based indexing)
- No redundancy between coords and attrs
- Full round-trip fidelity via preserved metadata dict

---

## Metadata Mapping Reference

### axes

**OME-NGFF Spec**: [§2.1 Axes](https://ngff.openmicroscopy.org/0.5/#axes-md)

OME-NGFF axes metadata describes the dimensions of the array.

| OME-NGFF Field | xarray Location | Notes |
|----------------|-----------------|-------|
| `axes[].name` | **Dataset.dims** | Axis names become dimension names (e.g., `['c', 'z', 'y', 'x']`) |
| `axes[].type` | `attrs['ome_axes_types']` | List of types (e.g., `['channel', 'space', 'space', 'space']`) |
| `axes[].unit` | `attrs['ome_axes_units']` | Dict mapping axis name to unit (e.g., `{'z': 'micrometer'}`) |

**Example:**

```python
ds = xr.open_dataset("image.ome.zarr", engine="ome-zarr")

# Axis names → dimensions
print(ds.dims)  # {'c': 2, 'z': 236, 'y': 275, 'x': 271}

# Axis types → attrs
print(ds.attrs['ome_axes_types'])  # ['channel', 'space', 'space', 'space']

# Axis units → attrs
print(ds.attrs['ome_axes_units'])  # {'z': 'micrometer', 'y': 'micrometer', 'x': 'micrometer'}
```

---

### coordinateTransformations

**OME-NGFF Spec**: [§2.3 Coordinate Transformations](https://ngff.openmicroscopy.org/0.5/#trafo-md)

Coordinate transformations define the mapping from array indices to physical coordinates.

| OME-NGFF Field | xarray Location | Notes |
|----------------|-----------------|-------|
| `scale` transformation | **Dataset.coords** | Converted to coordinate arrays via `translation + scale * arange(size)` |
| `translation` transformation | **Dataset.coords** | Offset applied to coordinate arrays |
| Original values | `attrs['ome_scale']`, `attrs['ome_translation']` | Preserved for efficient round-tripping |

**Example:**

```python
# OME-NGFF metadata:
# scale = {'z': 0.5, 'y': 0.36, 'x': 0.36}
# translation = {'z': 0.0, 'y': 0.0, 'x': 0.0}

ds = xr.open_dataset("image.ome.zarr", engine="ome-zarr")

# Coordinates derived from transforms
print(ds.coords['z'].values[:3])  # [0.0, 0.5, 1.0] (0 + 0.5 * [0,1,2,...])
print(ds.coords['y'].values[:3])  # [0.0, 0.36, 0.72]

# Original transforms preserved
print(ds.attrs['ome_scale'])  # {'z': 0.5, 'y': 0.36, 'x': 0.36}
```

**Round-trip:**

When writing, `coords_to_transforms()` extracts scale and translation from coordinates, or uses stored values for exact fidelity.

---

### multiscales

**OME-NGFF Spec**: [§2.4 Multiscales](https://ngff.openmicroscopy.org/0.5/#multiscale-md)

Multiscales metadata describes the image pyramid structure.

| OME-NGFF Field | xarray Location | Notes |
|----------------|-----------------|-------|
| `name` | `attrs['ome_name']` | Image identifier |
| `version` | `attrs['ome_version']` | OME-NGFF spec version |
| `type` | Not currently mapped | Downscaling method |
| `metadata` | Not currently mapped | Additional downscaling info |
| `datasets[].path` | `attrs['ome_multiscale_paths']` | List of resolution paths (e.g., `['0', '1', '2']`) |
| Number of datasets | `attrs['ome_num_resolutions']` | Count of resolution levels |
| `coordinateTransformations` | **Dataset.coords** (per dataset) | Applied per resolution level |

**Example:**

```python
dt = xr.open_datatree("image.ome.zarr", engine="ome-zarr")

# Multiscale info in root attrs
print(dt.attrs['ome_name'])  # 'image'
print(dt.attrs['ome_version'])  # '0.4'
print(dt.attrs['ome_num_resolutions'])  # 3
print(dt.attrs['ome_multiscale_paths'])  # ['0', '1', '2']

# Each resolution as a separate DataTree node
print(list(dt.children.keys()))  # ['scale0', 'scale1', 'scale2']
```

---

### omero

**OME-NGFF Spec**: [§2.5 OMERO Metadata (Transitional)](https://ngff.openmicroscopy.org/0.5/#omero-md)

OMERO metadata provides channel information and rendering settings.

| OME-NGFF Field | xarray Location | Notes |
|----------------|-----------------|-------|
| `omero.channels[].label` | **Dataset.coords['c']** | Channel labels as coordinate values (string dtype) |
| `omero.channels[].color` | `attrs['ome_channel_colors']` | List of hex color codes (e.g., `['0000FF', 'FFFF00']`) |
| `omero.channels[].window` | `attrs['ome_channel_windows']` | List of rendering window dicts |
| Other OMERO fields | `attrs['ome_ngff_metadata']['omero']` | Preserved in full metadata dict |

**Example:**

```python
ds = xr.open_dataset("image.ome.zarr", engine="ome-zarr")

# Channel labels → coordinates (PRIMARY LOCATION)
print(ds.coords['c'].values)  # array(['LaminB1', 'Dapi'], dtype='<U7')
print(ds.coords['c'].dtype)   # dtype('<U7')  (Unicode string)

# Select by channel name
lamin_data = ds.sel(c='LaminB1')

# Channel colors → attrs
print(ds.attrs['ome_channel_colors'])  # ['0000FF', 'FFFF00']

# Rendering windows → attrs
print(ds.attrs['ome_channel_windows'][0])
# {'min': 0.0, 'max': 65535.0, 'start': 0.0, 'end': 1500.0}
```

**Why channel labels are coordinates:**

Channel labels represent actual data dimensions, making them perfect for xarray coordinates:

```python
# Coordinate-based selection (natural xarray API)
ds.sel(c='DAPI')

# Coordinate-based filtering
ds.where(ds.c.isin(['DAPI', 'GFP']), drop=True)

# Coordinate-based iteration
for channel in ds.coords['c'].values:
    process(ds.sel(c=channel))
```

---

### labels

**OME-NGFF Spec**: [§2.6 Labels](https://ngff.openmicroscopy.org/0.5/#labels-md)

Label images are not yet supported. When implemented, they will likely be stored as separate DataArrays or referenced paths.

---

### plate / well

**OME-NGFF Spec**: [§2.7 Plate](https://ngff.openmicroscopy.org/0.5/#plate-md) | [§2.8 Well](https://ngff.openmicroscopy.org/0.5/#well-md)

HCS (High Content Screening) plate structures are not yet supported. See [TODO.md](../TODO.md) for implementation notes.

---

## Complete Attribute Reference

### Common Attributes (DataTree & Dataset)

These attributes are present in both DataTree root nodes and individual Datasets:

```python
attrs = {
    # Basic metadata
    'ome_name': 'image',                    # Image name
    'ome_version': '0.4',                   # OME-NGFF version

    # Axes information
    'ome_axes_types': ['channel', 'space', ...],  # Axis types
    'ome_axes_units': {'z': 'micrometer', ...},   # Physical units (optional)
    'ome_axes_orientations': {...},               # Anatomical orientations (optional)

    # Multiscale info
    'ome_num_resolutions': 3,                     # Number of pyramid levels
    'ome_multiscale_paths': ['0', '1', '2'],      # Resolution paths

    # Channel metadata (if channels present)
    'ome_channel_colors': ['0000FF', 'FFFF00'],   # Hex colors
    'ome_channel_windows': [{...}, {...}],        # Rendering windows

    # Complete metadata for round-tripping
    'ome_ngff_metadata': {...},                   # Full OME-NGFF metadata dict
}
```

### Dataset-Only Attributes

Datasets also contain coordinate transformation info:

```python
attrs = {
    # Coordinate transforms (for efficient round-trip)
    'ome_scale': {'c': 1.0, 'z': 0.5, ...},       # Scale factors
    'ome_translation': {'c': 0.0, 'z': 0.0, ...}, # Translation offsets

    # Resolution level (only in open_ome_dataset())
    'ome_ngff_resolution': 0,                     # Resolution index
}
```

---

## Round-Trip Fidelity

All metadata is preserved for perfect round-tripping:

```python
# Read
ds = xr.open_dataset("input.ome.zarr", engine="ome-zarr")

# Modify data (coords/attrs preserved automatically)
ds_modified = ds * 2

# Write - metadata reconstructed from coords + attrs
from xarray_ome import write_ome_dataset
write_ome_dataset(ds_modified, "output.ome.zarr")

# Verify
ds2 = xr.open_dataset("output.ome.zarr", engine="ome-zarr")
assert ds2.attrs['ome_ngff_metadata'] == ds.attrs['ome_ngff_metadata']
```

The full OME-NGFF metadata dict is always preserved in `attrs['ome_ngff_metadata']`, ensuring that even unknown or future metadata fields survive round-tripping.

---

## Implementation Details

### Conversion Functions

#### Reading: OME-NGFF → xarray

- `metadata_to_xarray_attrs()`: Extracts non-coordinate metadata to attrs
- `transforms_to_coords()`: Converts scale/translation to coordinate arrays
- `_extract_channel_labels()`: Gets channel labels from omero.channels

#### Writing: xarray → OME-NGFF

- `xarray_to_metadata()`: Reconstructs OME-NGFF metadata from attrs
- `coords_to_transforms()`: Extracts scale/translation from coordinates

See [xarray_ome/metadata.py](../xarray_ome/metadata.py) and [xarray_ome/transforms.py](../xarray_ome/transforms.py) for implementation.

---

## Version Support

**Reading**: All OME-NGFF versions (v0.1 - v0.5) via [ngff-zarr](https://ngff-zarr.readthedocs.io/)

**Writing**: v0.4 and v0.5 (current standard versions)

Version information is preserved in `attrs['ome_version']`.
