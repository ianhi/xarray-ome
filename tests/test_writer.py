"""Tests for xarray-ome writing functionality."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import xarray as xr

from xarray_ome import (
    open_ome_dataset,
    open_ome_datatree,
    write_ome_dataset,
    write_ome_datatree,
)

if TYPE_CHECKING:
    pass


def test_write_ome_dataset(tmp_ome_zarr: Path, tmp_path: Path) -> None:
    """Test writing a Dataset to OME-Zarr format."""
    # Read original
    ds_original = open_ome_dataset(str(tmp_ome_zarr))

    # Write to new location
    output_path = tmp_path / "written.ome.zarr"
    write_ome_dataset(ds_original, str(output_path))

    # Read back
    ds_written = open_ome_dataset(str(output_path))

    # Check dimensions match
    assert ds_written.dims == ds_original.dims

    # Check data variables match
    assert set(ds_written.data_vars) == set(ds_original.data_vars)

    # Check coordinates match (approximately - may have floating point differences)
    for coord_name in ds_original.coords:
        np.testing.assert_allclose(
            ds_written.coords[coord_name].values,
            ds_original.coords[coord_name].values,
            rtol=1e-5,
        )


def test_write_ome_dataset_with_scale_factors(
    tmp_ome_zarr_single_scale: Path, tmp_path: Path
) -> None:
    """Test writing a Dataset with multiscale pyramid generation."""
    # Read single scale
    ds = open_ome_dataset(str(tmp_ome_zarr_single_scale))

    # Write with scale factors to create pyramid
    output_path = tmp_path / "pyramid.ome.zarr"
    write_ome_dataset(ds, str(output_path), scale_factors=[2, 4])

    # Read back as DataTree to check pyramid
    dt = open_ome_datatree(str(output_path))

    # Should have 3 levels (original + 2 downsampled)
    assert len(dt.children) == 3
    assert "scale0" in dt.children
    assert "scale1" in dt.children
    assert "scale2" in dt.children

    # Get data variable name
    data_var_name = list(dt["scale0"].ds.data_vars.keys())[0]

    # Check sizes decrease
    shape0 = dt["scale0"].ds[data_var_name].shape
    shape1 = dt["scale1"].ds[data_var_name].shape
    shape2 = dt["scale2"].ds[data_var_name].shape

    assert shape1[0] < shape0[0]  # y dimension smaller
    assert shape1[1] < shape0[1]  # x dimension smaller
    assert shape2[0] < shape1[0]
    assert shape2[1] < shape1[1]


def test_write_ome_datatree(tmp_ome_zarr: Path, tmp_path: Path) -> None:
    """Test writing a DataTree to OME-Zarr format."""
    # Read original
    dt_original = open_ome_datatree(str(tmp_ome_zarr))

    # Write to new location
    output_path = tmp_path / "written_tree.ome.zarr"
    write_ome_datatree(dt_original, str(output_path))

    # Read back
    dt_written = open_ome_datatree(str(output_path))

    # Check number of scales match
    assert len(dt_written.children) == len(dt_original.children)

    # Check each scale
    for scale_name in dt_original.children.keys():
        assert scale_name in dt_written.children
        ds_orig = dt_original[scale_name].ds
        ds_written = dt_written[scale_name].ds

        # Check dimensions
        assert ds_written.dims == ds_orig.dims


def test_roundtrip_dataset(tmp_ome_zarr: Path, tmp_path: Path) -> None:
    """Test full round-trip: read -> write -> read."""
    # Read original
    ds1 = open_ome_dataset(str(tmp_ome_zarr))

    # Write
    output_path = tmp_path / "roundtrip.ome.zarr"
    write_ome_dataset(ds1, str(output_path))

    # Read back
    ds2 = open_ome_dataset(str(output_path))

    # Get data variable names
    data_var_name1 = list(ds1.data_vars.keys())[0]
    data_var_name2 = list(ds2.data_vars.keys())[0]

    # Check data matches (compute to compare actual values)
    data1 = ds1[data_var_name1].compute()
    data2 = ds2[data_var_name2].compute()
    np.testing.assert_array_equal(data1.values, data2.values)

    # Check metadata
    assert ds2.attrs["ome_scale"] == ds1.attrs["ome_scale"]
    assert ds2.attrs["ome_translation"] == ds1.attrs["ome_translation"]


def test_roundtrip_datatree(tmp_ome_zarr: Path, tmp_path: Path) -> None:
    """Test full round-trip for DataTree: read -> write -> read."""
    # Read original
    dt1 = open_ome_datatree(str(tmp_ome_zarr))

    # Write
    output_path = tmp_path / "roundtrip_tree.ome.zarr"
    write_ome_datatree(dt1, str(output_path))

    # Read back
    dt2 = open_ome_datatree(str(output_path))

    # Check all scales
    for scale_name in dt1.children.keys():
        ds1 = dt1[scale_name].ds
        ds2 = dt2[scale_name].ds

        # Get data variable names
        data_var_name1 = list(ds1.data_vars.keys())[0]
        data_var_name2 = list(ds2.data_vars.keys())[0]

        # Compute and compare data
        data1 = ds1[data_var_name1].compute()
        data2 = ds2[data_var_name2].compute()
        np.testing.assert_array_equal(data1.values, data2.values)


def test_write_preserves_metadata(tmp_ome_zarr: Path, tmp_path: Path) -> None:
    """Test that metadata is preserved through write operations."""
    # Read original
    ds_original = open_ome_dataset(str(tmp_ome_zarr))

    # Write
    output_path = tmp_path / "metadata_test.ome.zarr"
    write_ome_dataset(ds_original, str(output_path))

    # Read back
    ds_written = open_ome_dataset(str(output_path))

    # Check axes units are preserved
    assert ds_written.attrs["ome_axes_units"] == ds_original.attrs["ome_axes_units"]


def test_write_custom_chunks(tmp_ome_zarr_single_scale: Path, tmp_path: Path) -> None:
    """Test writing with custom chunk sizes."""
    ds = open_ome_dataset(str(tmp_ome_zarr_single_scale))

    # Write with custom chunks
    output_path = tmp_path / "custom_chunks.ome.zarr"
    write_ome_dataset(ds, str(output_path), chunks=(4, 4))

    # Read back - should work
    ds_written = open_ome_dataset(str(output_path))

    # Get data variable names
    data_var_name = list(ds.data_vars.keys())[0]
    data_var_name_written = list(ds_written.data_vars.keys())[0]

    assert ds_written[data_var_name_written].shape == ds[data_var_name].shape


def test_write_from_computed_data(tmp_path: Path) -> None:
    """Test writing from computed (non-lazy) data."""
    # Create a simple dataset with computed data
    data = np.arange(100, dtype=np.float32).reshape(10, 10)
    ds = xr.Dataset(
        {
            "image": (["y", "x"], data),
        },
        coords={
            "y": np.arange(10) * 0.5,
            "x": np.arange(10) * 0.5,
        },
    )

    # Add OME metadata
    ds.attrs["ome_scale"] = {"y": 0.5, "x": 0.5}
    ds.attrs["ome_translation"] = {"y": 0.0, "x": 0.0}

    # Write
    output_path = tmp_path / "computed_data.ome.zarr"
    write_ome_dataset(ds, str(output_path))

    # Read back
    ds_read = open_ome_dataset(str(output_path))

    # Check data matches
    np.testing.assert_array_equal(ds_read["image"].compute().values, data)
