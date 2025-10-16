"""Integration tests with real OME-NGFF sample data."""

import pytest
import xarray as xr

from xarray_ome import open_ome_dataset, open_ome_datatree

# Real OME-NGFF sample data from IDR
IDR_SAMPLE_URL = "https://uk1s3.embassy.ebi.ac.uk/idr/zarr/v0.4/idr0062A/6001240.zarr"


@pytest.mark.slow
def test_open_dataset_from_idr() -> None:
    """Test opening real OME-NGFF data from IDR using open_ome_dataset."""
    ds = open_ome_dataset(IDR_SAMPLE_URL)

    assert "image" in ds.data_vars
    assert ds["image"].shape == (2, 236, 275, 271)
    assert list(ds.dims.keys()) == ["c", "z", "y", "x"]

    assert "ome_scale" in ds.attrs
    assert "ome_translation" in ds.attrs
    assert "ome_axes_units" in ds.attrs


@pytest.mark.slow
def test_open_datatree_from_idr() -> None:
    """Test opening real OME-NGFF data from IDR using open_ome_datatree."""
    dt = open_ome_datatree(IDR_SAMPLE_URL)

    assert set(dt.children.keys()) == {"scale0", "scale1", "scale2"}

    scale0 = dt["scale0"].ds
    assert scale0 is not None
    assert scale0["image"].shape == (2, 236, 275, 271)

    scale1 = dt["scale1"].ds
    assert scale1 is not None
    assert scale1["image"].shape == (2, 236, 137, 135)

    scale2 = dt["scale2"].ds
    assert scale2 is not None
    assert scale2["image"].shape == (2, 236, 68, 67)

    assert "ome_ngff_metadata" in dt.attrs
    metadata = dt.attrs["ome_ngff_metadata"]
    assert metadata["version"] == "0.4"
    assert len(metadata["axes"]) == 4


@pytest.mark.slow
def test_backend_with_idr_dataset() -> None:
    """Test xarray backend with real IDR data using open_dataset."""
    ds = xr.open_dataset(IDR_SAMPLE_URL, engine="ome-zarr")

    assert "image" in ds.data_vars
    assert ds["image"].shape == (2, 236, 275, 271)
    assert list(ds.dims.keys()) == ["c", "z", "y", "x"]


@pytest.mark.slow
def test_backend_with_idr_datatree() -> None:
    """Test xarray backend with real IDR data using open_datatree."""
    dt = xr.open_datatree(IDR_SAMPLE_URL, engine="ome-zarr")

    assert len(dt.children) == 3
    assert "scale0" in dt.children
    assert "scale1" in dt.children
    assert "scale2" in dt.children

    scale0 = dt["scale0"].ds
    assert scale0 is not None
    assert scale0["image"].shape == (2, 236, 275, 271)


@pytest.mark.slow
def test_idr_data_coordinates() -> None:
    """Test that physical coordinates are correctly extracted from IDR data."""
    ds = open_ome_dataset(IDR_SAMPLE_URL)

    assert "c" in ds.coords
    assert "z" in ds.coords
    assert "y" in ds.coords
    assert "x" in ds.coords

    assert len(ds.coords["c"]) == 2
    assert len(ds.coords["z"]) == 236
    assert len(ds.coords["y"]) == 275
    assert len(ds.coords["x"]) == 271

    assert ds.attrs["ome_axes_units"]["z"] == "micrometer"
    assert ds.attrs["ome_axes_units"]["y"] == "micrometer"
    assert ds.attrs["ome_axes_units"]["x"] == "micrometer"


@pytest.mark.slow
def test_idr_lazy_loading() -> None:
    """Test that data is lazy-loaded and not fetched until compute."""
    import dask.array as da

    ds = xr.open_dataset(IDR_SAMPLE_URL, engine="ome-zarr")

    assert isinstance(ds["image"].data, da.Array)

    subset = ds["image"].isel(c=0, z=0)
    assert isinstance(subset.data, da.Array)

    computed = subset.compute()
    assert computed.shape == (275, 271)
