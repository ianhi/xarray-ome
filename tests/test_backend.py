"""Tests for xarray backend integration."""

from pathlib import Path

import xarray as xr

from xarray_ome import open_ome_dataset, open_ome_datatree


def test_backend_registered() -> None:
    """Test that ome-zarr backend is registered with xarray."""
    import xarray.backends.plugins as plugins

    backend = plugins.get_backend("ome-zarr")
    assert backend is not None
    assert backend.description == "Open OME-Zarr (OME-NGFF) files in xarray"


def test_open_dataset_with_backend(tmp_ome_zarr: Path) -> None:
    """Test opening dataset using xarray backend."""
    ds_backend = xr.open_dataset(str(tmp_ome_zarr), engine="ome-zarr")

    data_var_name = list(ds_backend.data_vars.keys())[0]

    assert ds_backend[data_var_name].shape == (2, 5, 10, 10)
    assert "c" in ds_backend.dims
    assert "z" in ds_backend.dims
    assert "y" in ds_backend.dims
    assert "x" in ds_backend.dims


def test_open_dataset_with_resolution(tmp_ome_zarr: Path) -> None:
    """Test opening specific resolution level using backend."""
    ds = xr.open_dataset(str(tmp_ome_zarr), engine="ome-zarr", resolution=1)

    data_var_name = list(ds.data_vars.keys())[0]

    assert ds[data_var_name].shape == (2, 2, 5, 5)


def test_open_datatree_with_backend(tmp_ome_zarr: Path) -> None:
    """Test opening DataTree using xarray backend."""
    dt_backend = xr.open_datatree(str(tmp_ome_zarr), engine="ome-zarr")

    assert "scale0" in dt_backend.children
    assert "scale1" in dt_backend.children
    assert "scale2" in dt_backend.children

    scale0 = dt_backend["scale0"].ds
    assert scale0 is not None

    data_var_name = list(scale0.data_vars.keys())[0]
    assert scale0[data_var_name].shape == (2, 5, 10, 10)


def test_backend_vs_direct_function_dataset(tmp_ome_zarr: Path) -> None:
    """Test that backend produces same result as direct function call."""
    ds_backend = xr.open_dataset(str(tmp_ome_zarr), engine="ome-zarr")
    ds_direct = open_ome_dataset(str(tmp_ome_zarr))

    data_var_backend = list(ds_backend.data_vars.keys())[0]
    data_var_direct = list(ds_direct.data_vars.keys())[0]

    assert ds_backend[data_var_backend].shape == ds_direct[data_var_direct].shape
    assert set(ds_backend.dims) == set(ds_direct.dims)


def test_backend_vs_direct_function_datatree(tmp_ome_zarr: Path) -> None:
    """Test that backend DataTree matches direct function."""
    dt_backend = xr.open_datatree(str(tmp_ome_zarr), engine="ome-zarr")
    dt_direct = open_ome_datatree(str(tmp_ome_zarr))

    assert set(dt_backend.children.keys()) == set(dt_direct.children.keys())

    for name in dt_backend.children.keys():
        ds_backend = dt_backend[name].ds
        ds_direct = dt_direct[name].ds

        assert ds_backend is not None
        assert ds_direct is not None

        data_var_backend = list(ds_backend.data_vars.keys())[0]
        data_var_direct = list(ds_direct.data_vars.keys())[0]

        assert ds_backend[data_var_backend].shape == ds_direct[data_var_direct].shape


def test_drop_variables_dataset(tmp_ome_zarr: Path) -> None:
    """Test drop_variables parameter with dataset."""
    ds_full = xr.open_dataset(str(tmp_ome_zarr), engine="ome-zarr")
    data_var_name = list(ds_full.data_vars.keys())[0]

    ds_dropped = xr.open_dataset(str(tmp_ome_zarr), engine="ome-zarr", drop_variables=data_var_name)

    assert data_var_name in ds_full.data_vars
    assert data_var_name not in ds_dropped.data_vars


def test_drop_variables_datatree(tmp_ome_zarr: Path) -> None:
    """Test drop_variables parameter with datatree."""
    dt_full = xr.open_datatree(str(tmp_ome_zarr), engine="ome-zarr")
    scale0_full = dt_full["scale0"].ds
    assert scale0_full is not None
    data_var_name = list(scale0_full.data_vars.keys())[0]

    dt_dropped = xr.open_datatree(
        str(tmp_ome_zarr), engine="ome-zarr", drop_variables=data_var_name
    )

    for name, child in dt_dropped.children.items():
        if child.ds is not None:
            assert data_var_name not in child.ds.data_vars


def test_guess_can_open(tmp_ome_zarr: Path) -> None:
    """Test that backend can identify OME-Zarr files."""
    from xarray_ome.backend import OmeZarrBackendEntrypoint

    backend = OmeZarrBackendEntrypoint()

    assert backend.guess_can_open(str(tmp_ome_zarr)) is True
    assert backend.guess_can_open("file.ome.zarr") is True
    assert backend.guess_can_open("file.zarr") is True
    assert backend.guess_can_open("file.nc") is False
    assert backend.guess_can_open(tmp_ome_zarr) is True
