"""Inspect the structure of an OME-Zarr file."""

import sys
from pathlib import Path

from xarray_ome import open_ome_datatree


def inspect_ome_zarr(path: Path) -> None:
    """Inspect and print information about an OME-Zarr file."""
    print(f"Inspecting: {path}")
    print("=" * 70)

    # Read the file
    dt = open_ome_datatree(path)

    # Print DataTree structure
    print("\nDataTree Structure:")
    print("-" * 70)
    print(dt)

    # Print metadata
    print("\nOME-NGFF Metadata:")
    print("-" * 70)
    metadata = dt.attrs.get("ome_ngff_metadata", {})
    if metadata:
        # Print top-level metadata keys
        for key, value in metadata.items():
            if isinstance(value, (list, dict)):
                print(f"{key}: {type(value).__name__} with {len(value)} items")
            else:
                print(f"{key}: {value}")
    else:
        print("No metadata found")

    # Print resolution levels
    print("\nResolution Levels:")
    print("-" * 70)
    for child_name, child_node in dt.children.items():
        ds = child_node.ds
        first_var = next(iter(ds.data_vars))
        data_array = ds[first_var]

        print(f"\n{child_name}:")
        print(f"  Dimensions: {dict(data_array.sizes)}")
        print(f"  Data type: {data_array.dtype}")
        print(f"  Chunk size: {data_array.chunks if hasattr(data_array, 'chunks') else 'N/A'}")

        # Print coordinate info
        print("  Coordinates:")
        for coord_name, coord in ds.coords.items():
            coord_min = float(coord.min())
            coord_max = float(coord.max())
            print(f"    {coord_name}: [{coord_min:.3f}, {coord_max:.3f}] ({len(coord)} points)")

        # Print scale/translation if available
        if "ome_scale" in ds.attrs:
            print(f"  Scale: {ds.attrs['ome_scale']}")
        if "ome_translation" in ds.attrs:
            print(f"  Translation: {ds.attrs['ome_translation']}")


def main() -> None:
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python inspect_structure.py <path/to/ome.zarr>")
        print("\nExample:")
        print("  python inspect_structure.py ~/data/sample.ome.zarr")
        sys.exit(1)

    path = Path(sys.argv[1])
    if not path.exists():
        print(f"Error: Path does not exist: {path}")
        sys.exit(1)

    inspect_ome_zarr(path)


if __name__ == "__main__":
    main()
