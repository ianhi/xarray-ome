# Usage Guide

xarray-ome provides seamless integration between OME-Zarr files and xarray's DataTree/Dataset structures.

## Installation

```bash
pip install xarray-ome
```

Or with uv:

```bash
uv add xarray-ome
```

## Sample Data

All examples in this documentation use real OME-NGFF sample data from the Image Data Resource (IDR). You can try these examples yourself without downloading any data - they work directly with remote URLs!

**Featured Sample Dataset:**

- **URL**: `https://uk1s3.embassy.ebi.ac.uk/idr/zarr/v0.4/idr0062A/6001240.zarr`
- **Dimensions**: 4D (2 channels × 236 z-slices × 275 y × 271 x)
- **Size**: Multi-resolution pyramid with 3 levels
- **Source**: [idr0062A - Drug treatment study](https://idr.openmicroscopy.org/webclient/?show=screen-1951)

Browse more sample datasets at: [OME-NGFF Samples](https://idr.github.io/ome-ngff-samples/)

## Basic Usage

### Opening OME-Zarr Files

xarray-ome provides two ways to open OME-Zarr files:

1. **Using dedicated functions** (`open_ome_datatree`, `open_ome_dataset`)
2. **Using xarray's native backend** (`xr.open_datatree`, `xr.open_dataset` with `engine="ome-zarr"`)

Both approaches provide the same functionality - use whichever fits your workflow better.

#### Using Xarray Backend (Recommended)

The most natural way to use xarray-ome is through xarray's native functions:

```python
import xarray as xr

# Open entire multiscale pyramid as DataTree
dt = xr.open_datatree("image.ome.zarr", engine="ome-zarr")

# Open single resolution level as Dataset
ds = xr.open_dataset("image.ome.zarr", engine="ome-zarr")

# Open specific resolution level
ds_low = xr.open_dataset("image.ome.zarr", engine="ome-zarr", resolution=2)

# Works with remote URLs too!
url = "https://uk1s3.embassy.ebi.ac.uk/idr/zarr/v0.4/idr0062A/6001240.zarr"
dt = xr.open_datatree(url, engine="ome-zarr")
```

#### Using Dedicated Functions

Alternatively, use the dedicated functions for more explicit control:

```python
from xarray_ome import open_ome_datatree, open_ome_dataset

# Open from local file
dt = open_ome_datatree("path/to/image.ome.zarr")

# Open from remote URL (using OME-NGFF sample data)
url = "https://uk1s3.embassy.ebi.ac.uk/idr/zarr/v0.4/idr0062A/6001240.zarr"
dt = open_ome_datatree(url)

# Access different resolution levels
print(dt.children.keys())  # dict_keys(['scale0', 'scale1', 'scale2'])

# Access highest resolution
high_res = dt["scale0"]

# Access lower resolution
low_res = dt["scale2"]

# Open specific resolution level
ds = open_ome_dataset("path/to/image.ome.zarr")
ds_low = open_ome_dataset("path/to/image.ome.zarr", resolution=2)

# Access data and coordinates
print(ds.dims)        # Dimensions: (c, z, y, x)
print(ds.coords)      # Physical coordinates in micrometers
print(ds.data_vars)   # Data variables
```

## Features

### Lazy Loading

xarray-ome supports lazy loading with Dask, enabling efficient work with large datasets:

```python
import xarray_ome

# Opening is fast - only metadata is read
ds = xarray_ome.open_ome_dataset("large_file.ome.zarr")

# Data is not loaded until needed
subset = ds.isel(z=slice(0, 10), y=slice(0, 100), x=slice(0, 100))

# Actually load the subset into memory
result = subset.compute()
```

### Remote Access

Read directly from remote URLs without downloading the entire file:

```python
from xarray_ome import open_ome_datatree

# Works with HTTP/HTTPS - using IDR OME-NGFF sample data
url = "https://uk1s3.embassy.ebi.ac.uk/idr/zarr/v0.4/idr0062A/6001240.zarr"
dt = open_ome_datatree(url)

# Only the chunks you access are downloaded
subset = dt["scale0"].ds.isel(z=0).compute()

# This downloads only ~few MB instead of the full dataset
print(f"Shape: {subset.dims}")
```

### Physical Coordinates

OME-NGFF coordinate transformations are automatically converted to xarray coordinates:

```python
ds = open_ome_dataset("image.ome.zarr")

# Coordinates represent physical space (e.g., micrometers)
print(ds.coords["x"])  # [0.0, 0.36, 0.72, ..., 97.31] micrometers
print(ds.coords["y"])  # [0.0, 0.36, 0.72, ..., 98.75] micrometers
print(ds.coords["z"])  # [0.0, 0.50, 1.00, ..., 117.5] micrometers

# Access metadata
print(ds.attrs["ome_scale"])        # Scale factors per dimension
print(ds.attrs["ome_translation"])  # Translation offsets
print(ds.attrs["ome_axes_units"])   # Physical units
```

## Metadata Handling

OME-NGFF metadata is preserved in the xarray attributes for round-tripping:

```python
dt = open_ome_datatree("image.ome.zarr")

# Access full OME-NGFF metadata
metadata = dt.attrs["ome_ngff_metadata"]
print(metadata["axes"])      # Axis definitions
print(metadata["datasets"])  # Dataset paths and transforms
print(metadata["version"])   # OME-NGFF version
```

## Working with DataTree

The DataTree structure preserves the multiscale pyramid:

```python
dt = open_ome_datatree("image.ome.zarr")

# Iterate through resolution levels
for name, child in dt.children.items():
    ds = child.ds
    print(f"{name}: {ds.dims}")

# Access as dictionary
scale0 = dt["scale0"].ds
scale1 = dt["scale1"].ds

# Use xarray operations on any level
mean_projection = scale0["image"].mean(dim="z")
```

## Advanced Usage

### Validation

Enable metadata validation against the OME-NGFF specification:

```python
# Validate metadata when opening
dt = open_ome_datatree("image.ome.zarr", validate=True)
ds = open_ome_dataset("image.ome.zarr", validate=True)
```

### Selecting Specific Regions

Use xarray's powerful indexing to work with subsets:

```python
ds = open_ome_dataset("large_image.ome.zarr")

# Select by dimension
channel_0 = ds.sel(c=0)

# Select by coordinate range
region = ds.sel(x=slice(10, 50), y=slice(20, 60))

# Integer indexing
slice_z10 = ds.isel(z=10)

# Combine operations
subset = ds.sel(c=0).isel(z=slice(0, 10)).mean(dim="z")
```

### Working with Dask

Take advantage of Dask for parallel and out-of-core computation:

```python
import dask

ds = open_ome_dataset("image.ome.zarr")

# Chain operations without loading data
result = (
    ds["image"]
    .sel(c=0)
    .mean(dim="z")
    .compute()  # Only compute at the end
)

# Configure Dask for parallel processing
with dask.config.set(scheduler="threads", num_workers=4):
    result = ds["image"].mean(dim=["y", "x"]).compute()
```

## Limitations

### Current Limitations

- **HCS/Plate structures not supported**: Only simple multiscale images are currently supported. High Content Screening (HCS) plate/well structures will raise an informative error.
- **Read-only**: Writing OME-Zarr files is not yet implemented.
- **OME-NGFF v0.4+**: Tested primarily with OME-NGFF versions 0.4 and 0.5.

### Error Handling

xarray-ome provides helpful error messages for unsupported formats:

```python
# Attempting to open an HCS plate
try:
    dt = open_ome_datatree("plate.ome.zarr")
except ValueError as e:
    print(e)
    # "The OME-Zarr store appears to be an HCS (High Content
    # Screening) plate structure, which is not yet supported."
```

## Examples

### Example: Multi-channel Z-stack

```python
from xarray_ome import open_ome_dataset
import matplotlib.pyplot as plt

# Open a multi-channel z-stack from IDR sample data
# This is a 4D image (c, z, y, x) from idr0062A
url = "https://uk1s3.embassy.ebi.ac.uk/idr/zarr/v0.4/idr0062A/6001240.zarr"
ds = open_ome_dataset(url)

# Create maximum intensity projection for first channel
mip = ds["image"].sel(c=0).max(dim="z")

# Plot
plt.imshow(mip, cmap="gray")
plt.title("Maximum Intensity Projection - Channel 0")
plt.xlabel("X (µm)")
plt.ylabel("Y (µm)")
plt.show()
```

### Example: Working with Multiple Resolutions

```python
from xarray_ome import open_ome_datatree

# Open all resolution levels from IDR sample data
url = "https://uk1s3.embassy.ebi.ac.uk/idr/zarr/v0.4/idr0062A/6001240.zarr"
dt = open_ome_datatree(url)

# Compare resolutions
for name, child in dt.children.items():
    ds = child.ds
    shape = ds["image"].shape
    print(f"{name}: {shape}")
# Output:
# scale0: (2, 236, 275, 271)
# scale1: (2, 118, 137, 135)
# scale2: (2, 59, 68, 67)

# Use lower resolution for quick preview
preview = dt["scale2"].ds["image"].sel(c=0, z=0).compute()

# Use high resolution for detailed analysis
high_res = dt["scale0"].ds["image"].sel(c=0, z=slice(0, 10))
```

### Example: Remote Data Processing

```python
from xarray_ome import open_ome_dataset

# Open remote OME-Zarr from IDR (no download required!)
url = "https://uk1s3.embassy.ebi.ac.uk/idr/zarr/v0.4/idr0062A/6001240.zarr"
ds = open_ome_dataset(url)

# Process a subset without downloading the full file
# Only downloads the chunks needed for this computation
result = (
    ds["image"]
    .sel(c=0)           # Select first channel
    .isel(z=slice(0, 10))  # Select first 10 z-slices
    .mean(dim="z")       # Average across z
    .compute()           # Execute computation
)

# Only the required chunks were downloaded (~few MB instead of full dataset)
print(f"Result shape: {result.shape}")  # (275, 271)
print(f"Result type: {type(result.values)}")  # numpy array
```

## API Reference

### Main Functions

```{eval-rst}
.. function:: open_ome_datatree(path, validate=False)

   Open an OME-Zarr store as an xarray DataTree.

   :param path: Path or URL to the OME-Zarr store
   :type path: str or pathlib.Path
   :param validate: Validate metadata against OME-NGFF spec
   :type validate: bool
   :return: DataTree with multiscale pyramid
   :rtype: xarray.DataTree
   :raises ValueError: If store is not a supported type

.. function:: open_ome_dataset(path, resolution=0, validate=False)

   Open a single resolution level as an xarray Dataset.

   :param path: Path or URL to the OME-Zarr store
   :type path: str or pathlib.Path
   :param resolution: Resolution level to open (0 is highest)
   :type resolution: int
   :param validate: Validate metadata against OME-NGFF spec
   :type validate: bool
   :return: Dataset with physical coordinates
   :rtype: xarray.Dataset
   :raises ValueError: If store is not a supported type or resolution not found
```

## See Also

- [OME-NGFF Specification](https://ngff.openmicroscopy.org/)
- [xarray Documentation](https://docs.xarray.dev/)
- [ngff-zarr Documentation](https://ngff-zarr.readthedocs.io/)
- [OME-NGFF Sample Data](https://idr.github.io/ome-ngff-samples/)
