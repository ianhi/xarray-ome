"""Basic example of reading OME-Zarr files with xarray-ome."""

from pathlib import Path

from xarray_ome import open_ome_dataset, open_ome_datatree


def main() -> None:
    """Run basic reading examples."""
    # Example 1: Read as DataTree (all resolution levels)
    print("Example 1: Reading as DataTree")
    print("-" * 50)

    # TODO: Replace with actual path to an OME-Zarr file
    # Download a sample from: https://idr.github.io/ome-ngff-samples/
    sample_path = Path("path/to/sample.ome.zarr")

    if not sample_path.exists():
        print(f"Sample file not found: {sample_path}")
        print("Please download a sample from https://idr.github.io/ome-ngff-samples/")
        return

    # Open as DataTree to get all resolution levels
    dt = open_ome_datatree(sample_path)
    print(f"DataTree structure:\n{dt}")
    print(f"\nRoot attrs: {dt.attrs.keys()}")

    # Iterate through resolution levels
    for child_name, child_node in dt.children.items():
        print(f"\n{child_name}:")
        print(f"  Shape: {child_node.ds.dims}")
        print(f"  Coordinates: {list(child_node.ds.coords.keys())}")

    # Example 2: Read single resolution level as Dataset
    print("\n" + "=" * 50)
    print("Example 2: Reading single resolution as Dataset")
    print("-" * 50)

    # Open highest resolution (level 0)
    ds = open_ome_dataset(sample_path, resolution=0)
    print(f"Dataset:\n{ds}")
    print("\nCoordinates:")
    for coord_name, coord in ds.coords.items():
        print(f"  {coord_name}: shape={coord.shape}, range=[{coord.min()}, {coord.max()}]")

    print(f"\nData variables: {list(ds.data_vars.keys())}")
    print(f"Attributes: {list(ds.attrs.keys())}")


if __name__ == "__main__":
    main()
