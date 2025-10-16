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

# xarray-ome

## Seamless integration between OME-Zarr and xarray

xarray-ome provides an xarray backend for reading OME-Zarr (OME-NGFF) files, enabling efficient access to multiscale bioimaging data with lazy loading and physical coordinates.

```{note}
**Powered by [ngff-zarr](https://ngff-zarr.readthedocs.io/)**

xarray-ome is built on top of ngff-zarr, which handles all OME-NGFF specification parsing and Zarr I/O. We focus on providing seamless xarray integration and coordinate transformations.
```

## Features

::::{grid} 2

:::{grid-item-card} 🚀 Easy to Use
Open OME-Zarr files with a single function call

```python
from xarray_ome import open_ome_datatree
dt = open_ome_datatree("image.ome.zarr")
```

:::

:::{grid-item-card} 📊 Multiscale Support
Access entire multiscale pyramids as DataTree structures

```python
high_res = dt["scale0"]
low_res = dt["scale2"]
```

:::

:::{grid-item-card} 🌍 Remote Access
Work with remote data without downloading

```python
# Try with real IDR sample data!
url = "https://uk1s3.embassy.ebi.ac.uk/idr/zarr/v0.4/idr0062A/6001240.zarr"
ds = open_ome_dataset(url)
```

:::

:::{grid-item-card} ⚡ Lazy Loading
Efficient processing with Dask integration

```python
# Only loads what you need
subset = ds.isel(z=0).compute()
```

:::

::::

## Quick Start

### Installation

```bash
pip install xarray-ome
```

### Basic Usage

Try it with real data from the Image Data Resource:

```{code-cell} ipython3
import xarray as xr

# Load remote OME-Zarr data (no download needed!)
url = "https://uk1s3.embassy.ebi.ac.uk/idr/zarr/v0.4/idr0062A/6001240.zarr"
ds = xr.open_dataset(url, engine="ome-zarr")

# View the dataset
ds
```

Notice the xarray Dataset with physical coordinates and channel labels:

- **Channel coordinates** use labels from metadata (`'LaminB1'`, `'Dapi'`) instead of indices
- **Physical coordinates** in micrometers for spatial dimensions (z, y, x)
- **Lazy loading** with Dask - data is only loaded when needed
- **OME metadata** preserved in attributes for round-tripping

Now work with the data using familiar xarray operations:

```{code-cell} ipython3
# Select by channel name
lamin = ds.sel(c='LaminB1')
print(f"LaminB1 channel shape: {lamin['image'].shape}")

# Create maximum intensity projection
mip = ds['image'].sel(c='Dapi').max(dim='z')
print(f"MIP shape: {mip.shape}")

# Process a subset (only downloads what you need!)
subset = ds.sel(c='Dapi').isel(z=slice(0, 10))
print(f"Subset shape: {subset['image'].shape}")
print(f"Subset size: {subset['image'].nbytes / 1e6:.1f} MB")
```

## Architecture

xarray-ome uses **ngff-zarr** for OME-Zarr I/O and focuses on the xarray integration:

```{mermaid}
graph LR
    A[User Code] --> B[xarray-ome API]
    B --> C[Coordinate Translation]
    C --> D[ngff-zarr]
    D --> E[zarr]
    E --> F[Storage]
```

- **ngff-zarr**: Handles OME-Zarr specification compliance and I/O
- **xarray-ome**: Converts coordinate transformations and builds xarray structures
- **zarr**: Provides chunked array storage with lazy loading

## Contents

```{toctree}
:maxdepth: 2

usage
examples
api
contributing
```

## Specification Support

**OME-NGFF Versions:**

- **Reading**: v0.1 through v0.5 (via ngff-zarr)
- **Writing**: v0.4 and v0.5 (via ngff-zarr)

**Data Structures:**

- ✅ Simple multiscale images
- ❌ HCS plate structures (not yet supported)

## Contributing

Contributions are welcome! See our [contributing guide](contributing.md) for details.

## License

MIT License. See LICENSE file for details.

## Acknowledgments

- Built on [ngff-zarr](https://ngff-zarr.readthedocs.io/) for OME-Zarr handling
- Inspired by [xarray-ome-ngff](https://github.com/JaneliaSciComp/xarray-ome-ngff) for coordinate transformation patterns
- Part of the OME-NGFF ecosystem

## Links

- **Documentation**: [xarray-ome.readthedocs.io](https://xarray-ome.readthedocs.io/)
- **Source Code**: [github.com/your-org/xarray-ome](https://github.com/your-org/xarray-ome)
- **Issue Tracker**: [github.com/your-org/xarray-ome/issues](https://github.com/your-org/xarray-ome/issues)
- **OME-NGFF Spec**: [ngff.openmicroscopy.org](https://ngff.openmicroscopy.org/)
