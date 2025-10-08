# API Reference

## Reading Functions

### open_ome_datatree

```python
open_ome_datatree(path: str | Path, validate: bool = False) -> xr.DataTree
```

Open an OME-Zarr store as an xarray DataTree containing all resolution levels.

**Parameters:**

- **path** : `str` or `pathlib.Path`

  Path to the OME-Zarr store. Can be:
  - Local directory path: `"path/to/image.ome.zarr"`
  - Remote HTTP/HTTPS URL: `"https://example.com/data.ome.zarr"`
  - S3 URL: `"s3://bucket/data.ome.zarr"`

- **validate** : `bool`, default `False`

  Whether to validate metadata against the OME-NGFF specification.

**Returns:**

- **DataTree**

  An xarray DataTree with:
  - Root node containing OME-NGFF metadata in attrs
  - Child nodes for each resolution level (`scale0`, `scale1`, etc.)
  - Physical coordinates derived from OME-NGFF transformations
  - Lazy-loaded Dask arrays for efficient memory usage

**Raises:**

- **ValueError**

  If the OME-Zarr store is not a supported type (e.g., HCS plate structure).

**Examples:**

```python
from xarray_ome import open_ome_datatree

# Open local file
dt = open_ome_datatree("image.ome.zarr")

# Access resolution levels
print(dt.children.keys())  # ['scale0', 'scale1', 'scale2']

# Get highest resolution dataset
high_res = dt["scale0"].ds

# Iterate through levels
for name, child in dt.children.items():
    print(f"{name}: {child.ds.dims}")
```

---

### open_ome_dataset

```python
open_ome_dataset(
    path: str | Path,
    resolution: int = 0,
    validate: bool = False
) -> xr.Dataset
```

Open a single resolution level from an OME-Zarr store as an xarray Dataset.

**Parameters:**

- **path** : `str` or `pathlib.Path`

  Path to the OME-Zarr store (local or remote).

- **resolution** : `int`, default `0`

  Which resolution level to open. `0` is the highest resolution.

- **validate** : `bool`, default `False`

  Whether to validate metadata against the OME-NGFF specification.

**Returns:**

- **Dataset**

  An xarray Dataset with:
  - Data variables containing the image data
  - Physical coordinates (scale and translation applied)
  - OME-NGFF metadata in attrs for round-tripping
  - Lazy-loaded Dask arrays

**Raises:**

- **ValueError**

  - If the OME-Zarr store is not a supported type
  - If the requested resolution level does not exist

**Examples:**

```python
from xarray_ome import open_ome_dataset

# Open highest resolution (default)
ds = open_ome_dataset("image.ome.zarr")

# Open specific resolution level
ds_low = open_ome_dataset("image.ome.zarr", resolution=2)

# Access data and coordinates
print(ds.dims)           # Dimensions: {c: 2, z: 236, y: 275, x: 271}
print(ds.coords["x"])    # Physical x coordinates in micrometers
print(ds["image"].shape) # Data array shape
```

---

## Writing Functions

### write_ome_dataset

```python
write_ome_dataset(
    dataset: xr.Dataset,
    path: str | Path,
    *,
    scale_factors: list[int] | None = None,
    chunks: int | tuple[int, ...] | None = None,
) -> None
```

Write an xarray Dataset to OME-Zarr format.

**Parameters:**

- **dataset** : `xr.Dataset`

  Dataset to write. Should contain image data as a data variable.

- **path** : `str` or `pathlib.Path`

  Output path for the OME-Zarr store.

- **scale_factors** : `list[int]`, optional

  Scale factors for multiscale pyramid generation. If None, writes only the provided resolution level. Example: `[2, 4]` creates two additional downsampled levels at 2x and 4x.

- **chunks** : `int` or `tuple[int, ...]`, optional

  Chunk sizes for the Zarr array. If None, uses ngff-zarr defaults.

**Notes:**

- Converts xarray coordinates to OME-NGFF coordinate transformations using `coords_to_transforms()`
- Extracts OME-NGFF metadata from dataset attrs if present
- Uses ngff-zarr for the actual writing

**Examples:**

```python
from xarray_ome import open_ome_dataset, write_ome_dataset

# Simple round-trip
ds = open_ome_dataset("input.ome.zarr")
write_ome_dataset(ds, "output.ome.zarr")

# Write with multiscale pyramid
write_ome_dataset(ds, "output.ome.zarr", scale_factors=[2, 4])

# Write with custom chunking
write_ome_dataset(ds, "output.ome.zarr", chunks=(1, 1, 64, 64, 64))
```

---

### write_ome_datatree

```python
write_ome_datatree(
    datatree: xr.DataTree,
    path: str | Path,
    *,
    chunks: int | tuple[int, ...] | None = None,
) -> None
```

Write an xarray DataTree to OME-Zarr format.

**Parameters:**

- **datatree** : `xr.DataTree`

  DataTree with multiscale pyramid structure to write. Child nodes should be named `"scale0"`, `"scale1"`, etc.

- **path** : `str` or `pathlib.Path`

  Output path for the OME-Zarr store.

- **chunks** : `int` or `tuple[int, ...]`, optional

  Chunk sizes for the Zarr arrays. If None, uses ngff-zarr defaults.

**Notes:**

- Extracts OME-NGFF metadata from datatree attrs
- Converts xarray coordinates back to OME-NGFF coordinate transformations
- Preserves the complete multiscale pyramid structure

**Expected DataTree Structure:**

```text
root (with ome_ngff_metadata in attrs)
├── scale0 (highest resolution)
├── scale1
├── scale2
└── ...
```

**Examples:**

```python
from xarray_ome import open_ome_datatree, write_ome_datatree

# Round-trip entire multiscale pyramid
dt = open_ome_datatree("input.ome.zarr")
write_ome_datatree(dt, "output.ome.zarr")

# Modify and write back
dt = open_ome_datatree("input.ome.zarr")
# ... modify data ...
write_ome_datatree(dt, "modified.ome.zarr")
```

---

## Metadata Attributes

### DataTree Attributes

When using `open_ome_datatree()`, the root node contains:

- **ome_ngff_metadata** : `dict`

  Complete OME-NGFF metadata including:
  - `axes`: Axis definitions (name, type, unit)
  - `datasets`: Dataset paths and coordinate transformations
  - `version`: OME-NGFF specification version
  - `name`: Image name
  - Additional metadata fields

### Dataset Attributes

Each Dataset (from `open_ome_dataset()` or DataTree child nodes) contains:

- **ome_scale** : `dict[str, float]`

  Scale factors for each dimension. Maps dimension names to scale values.
  Example: `{'c': 1.0, 'z': 0.5, 'y': 0.36, 'x': 0.36}`

- **ome_translation** : `dict[str, float]`

  Translation offsets for each dimension. Maps dimension names to offset values.
  Example: `{'c': 0.0, 'z': 0.0, 'y': 0.0, 'x': 0.0}`

- **ome_axes_units** : `dict[str, str | None]`

  Physical units for each dimension.
  Example: `{'c': None, 'z': 'micrometer', 'y': 'micrometer', 'x': 'micrometer'}`

- **ome_axes_orientations** : `dict[str, str]` (optional)

  Anatomical orientation for spatial axes (if RFC-4 metadata present).

- **ome_ngff_resolution** : `int`

  The resolution level index (only in Datasets from `open_ome_dataset()`).

- **ome_ngff_metadata** : `dict`

  Full OME-NGFF metadata (only in Datasets from `open_ome_dataset()`).

## Coordinate Transformations

### transforms_to_coords

```python
transforms_to_coords(
    shape: tuple[int, ...],
    dims: Sequence[str],
    scale: dict[str, float],
    translation: dict[str, float],
) -> dict[str, np.ndarray]
```

Convert OME-NGFF coordinate transformations to xarray coordinate arrays.

For each dimension, computes: `coords[dim] = translation[dim] + scale[dim] * np.arange(size[dim])`

**Parameters:**

- **shape** : `tuple[int, ...]` - Array shape
- **dims** : `Sequence[str]` - Dimension names (e.g., `['z', 'y', 'x']`)
- **scale** : `dict[str, float]` - Scale factors per dimension
- **translation** : `dict[str, float]` - Translation offsets per dimension

**Returns:**

- **dict[str, np.ndarray]** - Mapping of dimension names to coordinate arrays

---

### coords_to_transforms

```python
coords_to_transforms(
    dataset: xr.Dataset,
) -> tuple[dict[str, float], dict[str, float]]
```

Convert xarray coordinates back to OME-NGFF coordinate transformations.

Inverse of `transforms_to_coords()` for round-tripping. If OME metadata is stored in attrs, uses that directly. Otherwise, computes from coordinate arrays.

**Parameters:**

- **dataset** : `xr.Dataset` - Dataset with coordinate arrays

**Returns:**

- **scale** : `dict[str, float]` - Scale factors for each dimension
- **translation** : `dict[str, float]` - Translation offsets for each dimension

## Utilities

### Store Type Detection

Internal utility for detecting OME-Zarr store types:

```python
_detect_store_type(path: str) -> str
```

Returns `'image'`, `'hcs'`, or `'unknown'`.

Used internally to provide helpful error messages when unsupported store types are encountered.

## Type Definitions

### Common Types

- **Path-like**: `str | pathlib.Path` - Local file paths or URLs
- **Dimension names**: `str` - Common dimensions: `'t'` (time), `'c'` (channel), `'z'` (depth), `'y'`, `'x'`
- **Physical units**: `str` - Common units: `'micrometer'`, `'nanometer'`, `'second'`, etc.

### Data Structures

- **DataTree**: `xarray.DataTree` - Hierarchical structure for multiscale data
- **Dataset**: `xarray.Dataset` - Container for labeled multi-dimensional arrays
- **DataArray**: `xarray.DataArray` - Labeled multi-dimensional array (usually Dask array)

## See Also

- [xarray.DataTree documentation](https://docs.xarray.dev/en/latest/user-guide/hierarchical-data.html)
- [xarray.Dataset documentation](https://docs.xarray.dev/en/stable/generated/xarray.Dataset.html)
- [OME-NGFF specification](https://ngff.openmicroscopy.org/)
