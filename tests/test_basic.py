"""Basic tests for xarray-ome reading functionality."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import pytest
import xarray as xr

from xarray_ome import open_ome_dataset, open_ome_datatree

if TYPE_CHECKING:
    pass


def test_imports() -> None:
    """Test that imports work."""
    assert open_ome_dataset is not None
    assert open_ome_datatree is not None


def test_open_ome_dataset(tmp_ome_zarr: Path) -> None:
    """Test opening an OME-Zarr file as a Dataset."""
    ds = open_ome_dataset(str(tmp_ome_zarr))

    # Check it's a Dataset
    assert isinstance(ds, xr.Dataset)

    # Check dimensions
    assert "c" in ds.dims
    assert "z" in ds.dims
    assert "y" in ds.dims
    assert "x" in ds.dims

    # Check data variable exists
    data_vars = list(ds.data_vars.keys())
    assert len(data_vars) > 0
    data_var_name = data_vars[0]

    # Check shape
    assert ds[data_var_name].shape == (2, 5, 10, 10)

    # Check coordinates exist
    assert "c" in ds.coords
    assert "z" in ds.coords
    assert "y" in ds.coords
    assert "x" in ds.coords

    # Check metadata is present
    assert "ome_scale" in ds.attrs
    assert "ome_translation" in ds.attrs
    assert "ome_axes_units" in ds.attrs
    assert "ome_ngff_resolution" in ds.attrs
    assert "ome_ngff_metadata" in ds.attrs


def test_open_ome_datatree(tmp_ome_zarr: Path) -> None:
    """Test opening an OME-Zarr file as a DataTree."""
    dt = open_ome_datatree(str(tmp_ome_zarr))

    # Check it's a DataTree
    assert isinstance(dt, xr.DataTree)

    # Check children exist (should have 3 scales: 0, 1, 2)
    assert len(dt.children) == 3
    assert "scale0" in dt.children
    assert "scale1" in dt.children
    assert "scale2" in dt.children

    # Check metadata is present in root
    assert "ome_ngff_metadata" in dt.attrs

    # Check each scale level
    for scale_name, expected_shape in [
        ("scale0", (2, 5, 10, 10)),
        ("scale1", (2, 3, 5, 5)),
        ("scale2", (2, 2, 3, 3)),
    ]:
        child = dt[scale_name]
        ds = child.ds
        assert ds is not None
        data_vars = list(ds.data_vars.keys())
        assert len(data_vars) > 0
        data_var_name = data_vars[0]
        # Check shape (approximately - depends on downsampling method)
        actual_shape = ds[data_var_name].shape
        assert actual_shape[0] == expected_shape[0]  # c dimension
        assert actual_shape[1] <= expected_shape[1]  # z dimension (approx)


def test_open_ome_dataset_specific_resolution(tmp_ome_zarr: Path) -> None:
    """Test opening a specific resolution level."""
    # Open resolution level 1
    ds = open_ome_dataset(str(tmp_ome_zarr), resolution=1)

    # Get data variable name
    data_var_name = list(ds.data_vars.keys())[0]

    # Check it's downsampled
    assert ds[data_var_name].shape[0] == 2  # c dimension same
    assert ds[data_var_name].shape[2] < 10  # y dimension smaller
    assert ds[data_var_name].shape[3] < 10  # x dimension smaller

    # Check metadata
    assert ds.attrs["ome_ngff_resolution"] == 1


def test_open_ome_dataset_invalid_resolution(tmp_ome_zarr: Path) -> None:
    """Test opening an invalid resolution level raises error."""
    with pytest.raises(ValueError, match="Resolution level 10 not found"):
        open_ome_dataset(str(tmp_ome_zarr), resolution=10)


def test_physical_coordinates(tmp_ome_zarr: Path) -> None:
    """Test that physical coordinates are correctly applied."""
    ds = open_ome_dataset(str(tmp_ome_zarr))

    # Check z coordinates (scale=0.5, translation=0.0)
    z_coords = ds.coords["z"].values
    assert len(z_coords) == 5
    assert z_coords[0] == 0.0
    assert z_coords[1] == 0.5
    assert z_coords[2] == 1.0

    # Check y coordinates (scale=0.25, translation=0.0)
    y_coords = ds.coords["y"].values
    assert len(y_coords) == 10
    assert y_coords[0] == 0.0
    assert y_coords[1] == 0.25
    assert y_coords[2] == 0.5

    # Check x coordinates (scale=0.25, translation=0.0)
    x_coords = ds.coords["x"].values
    assert len(x_coords) == 10
    assert x_coords[0] == 0.0
    assert x_coords[1] == 0.25


def test_lazy_loading(tmp_ome_zarr: Path) -> None:
    """Test that data is lazily loaded with Dask."""
    ds = open_ome_dataset(str(tmp_ome_zarr))

    # Get data variable name
    data_var_name = list(ds.data_vars.keys())[0]

    # Data should be a Dask array
    data_array = ds[data_var_name]
    assert hasattr(data_array.data, "compute")  # Dask arrays have compute method

    # Compute a subset
    subset = data_array.isel(c=0, z=0).compute()
    assert isinstance(subset.values, np.ndarray)
    assert subset.shape == (10, 10)


def test_single_scale_file(tmp_ome_zarr_single_scale: Path) -> None:
    """Test opening a single-scale OME-Zarr file."""
    ds = open_ome_dataset(str(tmp_ome_zarr_single_scale))

    # Get data variable name
    data_var_name = list(ds.data_vars.keys())[0]

    # Check dimensions
    assert ds[data_var_name].shape == (8, 8)
    assert "y" in ds.dims
    assert "x" in ds.dims

    # DataTree should have only one scale
    dt = open_ome_datatree(str(tmp_ome_zarr_single_scale))
    assert len(dt.children) == 1
    assert "scale0" in dt.children
