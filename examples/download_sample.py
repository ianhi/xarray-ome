"""Download a sample OME-Zarr file for testing."""

import sys
from pathlib import Path

from ngff_zarr import from_ngff_zarr, to_ngff_zarr


def download_sample(
    url: str = "https://uk1s3.embassy.ebi.ac.uk/idr/zarr/v0.5/idr0062A/6001240_labels.zarr",
    output_path: str = "data/6001240_labels.zarr",
) -> None:
    """
    Download an OME-Zarr file from a URL and save it locally.

    Parameters
    ----------
    url : str
        URL to the OME-Zarr store
    output_path : str
        Local path to save the file
    """
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    print(f"Downloading from: {url}")
    print(f"Saving to: {output}")

    multiscales = from_ngff_zarr(url)

    print(f"\nFound {len(multiscales.images)} resolution levels")
    for i, img in enumerate(multiscales.images):
        print(f"  Level {i}: shape={img.data.shape}, dims={img.dims}")

    print("\nSaving to disk...")
    to_ngff_zarr(str(output), multiscales)

    print(f"✓ Download complete: {output}")
    print(
        f"  Size: {sum(f.stat().st_size for f in output.rglob('*') if f.is_file()) / 1024 / 1024:.2f} MB"
    )


def main() -> None:
    """Main entry point."""
    url = "https://uk1s3.embassy.ebi.ac.uk/idr/zarr/v0.5/idr0062A/6001240_labels.zarr"
    output = "data/6001240_labels.zarr"

    if len(sys.argv) > 1:
        url = sys.argv[1]
    if len(sys.argv) > 2:
        output = sys.argv[2]

    download_sample(url, output)


if __name__ == "__main__":
    main()
