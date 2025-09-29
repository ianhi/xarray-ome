"""Basic tests for xarray-ome reading functionality."""

import pytest

from xarray_ome import open_ome_dataset, open_ome_datatree


def test_imports() -> None:
    """Test that imports work."""
    assert open_ome_dataset is not None
    assert open_ome_datatree is not None


@pytest.mark.skip(reason="Need sample OME-Zarr file")
def test_open_ome_dataset() -> None:
    """Test opening an OME-Zarr file as a Dataset."""
    # Will implement once we have a sample file
    pass


@pytest.mark.skip(reason="Need sample OME-Zarr file")
def test_open_ome_datatree() -> None:
    """Test opening an OME-Zarr file as a DataTree."""
    # Will implement once we have a sample file
    pass
