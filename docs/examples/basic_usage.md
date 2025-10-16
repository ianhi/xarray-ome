---
jupytext:
  formats: md:myst
  text_representation:
    extension: .md
    format_name: myst
kernelspec:
  display_name: Python 3
  language: python
  name: python3
---

# Basic Usage

This example demonstrates the fundamental operations for reading OME-Zarr files with xarray-ome.

## Opening OME-Zarr Files

There are two main ways to open OME-Zarr files:

1. As a **DataTree** - contains all resolution levels
2. As a **Dataset** - contains a single resolution level

```{code-cell} ipython3
import xarray as xr
from xarray_ome import open_ome_dataset, open_ome_datatree

# Sample data from the Image Data Resource
url = "https://uk1s3.embassy.ebi.ac.uk/idr/zarr/v0.4/idr0062A/6001240.zarr"
```

## Opening as Dataset

Open a single resolution level (default is highest resolution):

```{code-cell} ipython3
# Open highest resolution (default)
ds = open_ome_dataset(url)

print("Dataset dimensions:", dict(ds.sizes))
print("Data variables:", list(ds.data_vars.keys()))
print("Coordinate names:", list(ds.coords.keys()))
```

## Exploring Coordinates

OME-NGFF coordinate transformations are converted to xarray coordinates:

```{code-cell} ipython3
# Show coordinate details
print("\nCoordinate ranges:")
for name, coord in ds.coords.items():
    print(f"{name}: {coord.shape[0]} points")
    if name in ['x', 'y', 'z']:
        unit = ds.attrs['ome_axes_units'].get(name, 'unknown')
        print(f"  Range: [{float(coord.min()):.2f}, {float(coord.max()):.2f}] {unit}")
```

## Opening as DataTree

Open all resolution levels in the multiscale pyramid:

```{code-cell} ipython3
# Open as DataTree to get all resolutions
dt = open_ome_datatree(url)

print("\nDataTree structure:")
print(f"Root node: {dt.name}")
print(f"Children: {list(dt.children.keys())}")

# Show shape of each resolution level
print("\nResolution levels:")
for name, child in dt.children.items():
    shape = child.ds['image'].shape
    print(f"  {name}: {shape}")
```

## Accessing Different Resolutions

```{code-cell} ipython3
# Access highest resolution from DataTree
high_res = dt["scale0"].ds
print(f"Highest resolution: {high_res['image'].shape}")

# Access lower resolution for quick previews
low_res = dt["scale2"].ds
print(f"Lowest resolution: {low_res['image'].shape}")
```

## Using xarray's Native Backend

You can also use xarray's native functions with the `engine="ome-zarr"` parameter:

```{code-cell} ipython3
# Using xarray's native functions
ds_native = xr.open_dataset(url, engine="ome-zarr")
dt_native = xr.open_datatree(url, engine="ome-zarr")

print(f"\nUsing native xarray backend:")
print(f"Dataset: {ds_native['image'].shape}")
print(f"DataTree: {list(dt_native.children.keys())}")
```

## Lazy Loading

Data is loaded lazily with Dask - only metadata is read initially:

```{code-cell} ipython3
import dask

print(f"Data type: {type(ds['image'].data)}")
print(f"Is Dask array: {isinstance(ds['image'].data, dask.array.Array)}")

# Data is only loaded when .compute() is called
print(f"\nChunk size: {ds['image'].data.chunksize}")
```

## Selecting Subsets

Use xarray's powerful indexing to work with subsets:

```{code-cell} ipython3
# Select single channel
channel_0 = ds.sel(c='LaminB1')
print(f"Single channel shape: {channel_0['image'].shape}")

# Select z-slice
z_slice = ds.isel(z=100)
print(f"Z-slice shape: {z_slice['image'].shape}")

# Combine selections
subset = ds.sel(c='Dapi').isel(z=slice(0, 10))
print(f"Subset shape: {subset['image'].shape}")
```

## Computing Results

Load data into memory when needed:

```{code-cell} ipython3
# Create a maximum intensity projection (lazy operation)
mip = ds['image'].sel(c='LaminB1').max(dim='z')
print(f"MIP (lazy): {type(mip.data)}")

# Compute the result
mip_computed = mip.compute()
print(f"MIP (computed): {type(mip_computed.data)}")
print(f"MIP shape: {mip_computed.shape}")
```

## Metadata Access

All OME-NGFF metadata is preserved in attributes:

```{code-cell} ipython3
print("\nMetadata attributes:")
print(f"  Image name: {ds.attrs.get('ome_image_name')}")
print(f"  OME-NGFF version: {ds.attrs['ome_ngff_metadata']['version']}")
print(f"  Axes units: {ds.attrs['ome_axes_units']}")
print(f"  Scale factors: {ds.attrs['ome_scale']}")
```
