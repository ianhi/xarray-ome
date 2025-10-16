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

# Working with Channel Labels

This example demonstrates how xarray-ome automatically extracts channel labels from OME-NGFF metadata and uses them as coordinate values.

## Loading Data with Channel Labels

We'll use a real sample from the Image Data Resource (IDR) that includes channel metadata:

```{code-cell} ipython3
import xarray_ome as xo

# Load IDR sample with channel labels
url = "https://uk1s3.embassy.ebi.ac.uk/idr/zarr/v0.4/idr0062A/6001240.zarr"

print("Loading OME-Zarr from IDR...")
ds = xo.open_ome_dataset(url)

print(f"\nDimensions: {dict(ds.sizes)}")
print(f"Data shape: {ds['image'].shape}")
```

## Channel Coordinates

Notice how channel coordinates use the labels from metadata instead of numeric indices:

```{code-cell} ipython3
# Channel coordinates use labels from metadata
print("Channel coordinates:", ds.coords['c'].values)

# These labels are also stored in attrs
print("Channel labels (from attrs):", ds.attrs.get('ome_channel_labels'))
```

## Selecting by Channel Name

With labeled channels, you can select data using meaningful names:

```{code-cell} ipython3
# Select by channel name
for channel in ds.coords["c"].values:
    channel_data = ds.sel(c=channel)
    print(f"\n{channel}:")
    print(f"  Shape: {channel_data['image'].shape}")
    print(f"  Data type: {channel_data['image'].dtype}")
```

## Physical Coordinates

The dataset also includes physical coordinates with units:

```{code-cell} ipython3
# Show physical coordinates and units
for coord_name in ["z", "y", "x"]:
    coord = ds.coords[coord_name]
    unit = ds.attrs['ome_axes_units'][coord_name]
    spacing = coord[1].values - coord[0].values if len(coord) > 1 else 0

    print(f"\n{coord_name}:")
    print(f"  Unit: {unit}")
    print(f"  Range: [{coord.min().values:.2f}, {coord.max().values:.2f}]")
    print(f"  Spacing: {spacing:.4f}")
```

## Metadata

All OME-NGFF metadata is preserved in the dataset attributes:

```{code-cell} ipython3
print("Image name:", ds.attrs.get('ome_image_name'))
print("OME-NGFF version:", ds.attrs['ome_ngff_metadata']['version'])
print("Resolution level:", ds.attrs.get('ome_ngff_resolution'))
```

## Selecting Data by Channel Name

You can use the channel labels for intuitive data selection:

```{code-cell} ipython3
# Get just the LaminB1 channel
lamin_data = ds.sel(c='LaminB1')
print(f"LaminB1 shape: {lamin_data['image'].shape}")

# Get just the Dapi channel
dapi_data = ds.sel(c='Dapi')
print(f"Dapi shape: {dapi_data['image'].shape}")

# Get a single z-slice of the Dapi channel
dapi_slice = ds.sel(c='Dapi').isel(z=100)
print(f"Dapi z-slice shape: {dapi_slice['image'].shape}")
```

## Notes

- Channel labels are extracted from `omero.channels[].label` in the OME-NGFF metadata
- This field is marked as "transitional" in the spec but is the only standard location for channel labels
- Works across all OME-NGFF versions (v0.1-v0.5)
- If labels are missing, defaults to `channel_0`, `channel_1`, etc.
