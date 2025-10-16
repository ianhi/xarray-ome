"""Example loading IDR data with channel labels."""

import xarray_ome as xo


def main() -> None:
    """Load IDR sample data and demonstrate channel label usage."""
    # Load IDR sample with channel labels
    url = "https://uk1s3.embassy.ebi.ac.uk/idr/zarr/v0.4/idr0062A/6001240.zarr"

    print("Loading OME-Zarr from IDR...")
    ds = xo.open_ome_dataset(url)

    print("\n" + "=" * 60)
    print("Dataset Information")
    print("=" * 60)

    print(f"\nDimensions: {dict(ds.sizes)}")
    print(f"Data shape: {ds['image'].shape}")

    print("\n" + "-" * 60)
    print("Channel Information")
    print("-" * 60)

    # Show channel coordinates (using labels from metadata)
    print(f"\nChannel coordinates: {ds.coords['c'].values}")
    print(f"Channel labels (from attrs): {ds.attrs.get('ome_channel_labels')}")

    # Show how to select by channel name
    print("\n" + "-" * 60)
    print("Selecting by Channel Name")
    print("-" * 60)

    for channel in ds.coords["c"].values:
        channel_data = ds.sel(c=channel)
        print(f"\n{channel}:")
        print(f"  Shape: {channel_data['image'].shape}")
        print(f"  Data type: {channel_data['image'].dtype}")

    print("\n" + "-" * 60)
    print("Physical Coordinates")
    print("-" * 60)

    # Show physical coordinates
    for coord_name in ["z", "y", "x"]:
        coord = ds.coords[coord_name]
        print(f"\n{coord_name}:")
        print(f"  Unit: {ds.attrs['ome_axes_units'][coord_name]}")
        print(f"  Range: [{coord.min().values:.2f}, {coord.max().values:.2f}]")
        print(f"  Spacing: {coord[1].values - coord[0].values:.4f}")

    print("\n" + "-" * 60)
    print("Metadata Attributes")
    print("-" * 60)

    print(f"\nImage name: {ds.attrs.get('ome_image_name')}")
    print(f"OME-NGFF version: {ds.attrs['ome_ngff_metadata']['version']}")
    print(f"Resolution level: {ds.attrs.get('ome_ngff_resolution')}")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
