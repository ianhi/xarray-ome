"""Tests for xarray-ngff writing functionality."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import xarray as xr

from xarray_ngff import (
    open_ngff_dataset,
    open_ngff_datatree,
    write_ngff_dataset,
    write_ngff_datatree,
)
from xarray_ngff.writer import deep_merge


def test_deep_merge_replaces_list_values() -> None:
    """A list value (e.g. `multiscales`) is replaced wholesale, not element-merged."""
    base = {"multiscales": [{"a": 1}, {"b": 2}], "omero": {"channels": [1, 2, 3]}}
    override = {"multiscales": [{"c": 3}]}

    merged = deep_merge(base, override)

    # multiscales list is fully replaced by the override
    assert merged["multiscales"] == [{"c": 3}]
    # unrelated keys are preserved
    assert merged["omero"] == {"channels": [1, 2, 3]}
    # inputs are not mutated
    assert base["multiscales"] == [{"a": 1}, {"b": 2}]


if TYPE_CHECKING:
    pass


def test_write_ngff_dataset(tmp_ome_zarr: Path, tmp_path: Path) -> None:
    """Test writing a Dataset to OME-Zarr format."""
    # Read original
    ds_original = open_ngff_dataset(str(tmp_ome_zarr))

    # Write to new location
    output_path = tmp_path / "written.ome.zarr"
    write_ngff_dataset(ds_original, str(output_path))

    # Read back
    ds_written = open_ngff_dataset(str(output_path))

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


def test_write_ngff_dataset_with_scale_factors(
    tmp_ome_zarr_single_scale: Path, tmp_path: Path
) -> None:
    """Test writing a Dataset with multiscale pyramid generation."""
    # Read single scale
    ds = open_ngff_dataset(str(tmp_ome_zarr_single_scale))

    # Write with scale factors to create pyramid
    output_path = tmp_path / "pyramid.ome.zarr"
    write_ngff_dataset(ds, str(output_path), scale_factors=[2, 4])

    # Read back as DataTree to check pyramid
    dt = open_ngff_datatree(str(output_path))

    # Should have 3 levels (original + 2 downsampled), named by level index.
    assert len(dt.children) == 3
    assert "0" in dt.children
    assert "1" in dt.children
    assert "2" in dt.children

    # Get data variable name
    data_var_name = list(dt["0"].ds.data_vars.keys())[0]

    # Check sizes decrease
    shape0 = dt["0"].ds[data_var_name].shape
    shape1 = dt["1"].ds[data_var_name].shape
    shape2 = dt["2"].ds[data_var_name].shape

    assert shape1[0] < shape0[0]  # y dimension smaller
    assert shape1[1] < shape0[1]  # x dimension smaller
    assert shape2[0] < shape1[0]
    assert shape2[1] < shape1[1]


def test_write_ngff_datatree(tmp_ome_zarr: Path, tmp_path: Path) -> None:
    """Test writing a DataTree to OME-Zarr format."""
    # Read original
    dt_original = open_ngff_datatree(str(tmp_ome_zarr))

    # Write to new location
    output_path = tmp_path / "written_tree.ome.zarr"
    write_ngff_datatree(dt_original, str(output_path))

    # Read back
    dt_written = open_ngff_datatree(str(output_path))

    # Check number of scales match
    assert len(dt_written.children) == len(dt_original.children)

    # Check each scale by comparing sorted children
    # Note: Node names may differ (e.g., "scale0_test_image" vs "scale0_image")
    # but the scales should match in order
    orig_scales = sorted(dt_original.children.items())
    written_scales = sorted(dt_written.children.items())

    for (orig_name, orig_child), (written_name, written_child) in zip(orig_scales, written_scales):
        ds_orig = orig_child.ds
        ds_written = written_child.ds

        # Check dimensions match
        assert ds_written.dims == ds_orig.dims


def test_roundtrip_dataset(tmp_ome_zarr: Path, tmp_path: Path) -> None:
    """Test full round-trip: read -> write -> read."""
    # Read original
    ds1 = open_ngff_dataset(str(tmp_ome_zarr))

    # Write
    output_path = tmp_path / "roundtrip.ome.zarr"
    write_ngff_dataset(ds1, str(output_path))

    # Read back
    ds2 = open_ngff_dataset(str(output_path))

    # Get data variable names
    data_var_name1 = list(ds1.data_vars.keys())[0]
    data_var_name2 = list(ds2.data_vars.keys())[0]

    # Check data matches (compute to compare actual values)
    data1 = ds1[data_var_name1].compute()
    data2 = ds2[data_var_name2].compute()
    np.testing.assert_array_equal(data1.values, data2.values)

    # NEW contract: physical coords survive the round-trip (writer derives
    # scale/translation from the lazy coords, reader rebuilds them).
    for axis in ("z", "y", "x"):
        np.testing.assert_allclose(ds2.coords[axis].values, ds1.coords[axis].values, rtol=1e-5)
    # Units survive via CF `units` coord attrs.
    assert ds2["z"].attrs.get("units") == ds1["z"].attrs.get("units")


def test_roundtrip_datatree(tmp_ome_zarr: Path, tmp_path: Path) -> None:
    """Test full round-trip for DataTree: read -> write -> read."""
    # Read original
    dt1 = open_ngff_datatree(str(tmp_ome_zarr))

    # Write
    output_path = tmp_path / "roundtrip_tree.ome.zarr"
    write_ngff_datatree(dt1, str(output_path))

    # Read back
    dt2 = open_ngff_datatree(str(output_path))

    # Check all scales by comparing sorted children
    # Note: Node names may differ after round-trip
    assert len(dt2.children) == len(dt1.children)
    scales1 = sorted(dt1.children.items())
    scales2 = sorted(dt2.children.items())

    for (name1, child1), (name2, child2) in zip(scales1, scales2):
        ds1 = child1.ds
        ds2 = child2.ds

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
    ds_original = open_ngff_dataset(str(tmp_ome_zarr))

    # Write
    output_path = tmp_path / "metadata_test.ome.zarr"
    write_ngff_dataset(ds_original, str(output_path))

    # Read back
    ds_written = open_ngff_dataset(str(output_path))

    # NEW contract: axes units live as CF `units` coord attrs and survive write.
    for axis in ("z", "y", "x"):
        assert ds_written[axis].attrs.get("units") == ds_original[axis].attrs.get("units")


def test_write_custom_chunks(tmp_ome_zarr_single_scale: Path, tmp_path: Path) -> None:
    """Test writing with custom chunk sizes."""
    ds = open_ngff_dataset(str(tmp_ome_zarr_single_scale))

    # Write with custom chunks
    output_path = tmp_path / "custom_chunks.ome.zarr"
    write_ngff_dataset(ds, str(output_path), chunks=(4, 4))

    # Read back - should work
    ds_written = open_ngff_dataset(str(output_path))

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

    # Write (scale/translation are derived from the coordinate arrays)
    output_path = tmp_path / "computed_data.ome.zarr"
    write_ngff_dataset(ds, str(output_path))

    # Read back
    ds_read = open_ngff_dataset(str(output_path))

    # Check data matches
    np.testing.assert_array_equal(ds_read["image"].compute().values, data)
