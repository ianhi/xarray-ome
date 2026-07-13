"""Integration tests with real OME-NGFF sample data (live IDR, network)."""

import pytest
import xarray as xr

from xarray_ngff import open_ngff_dataset, open_ngff_datatree
from xarray_ngff.indexes import TransformIndex

# Real OME-NGFF sample data from IDR (NGFF 0.4, 4-D c,z,y,x, carries omero channels).
IDR_SAMPLE_URL = "https://uk1s3.embassy.ebi.ac.uk/idr/zarr/v0.4/idr0062A/6001240.zarr"


def _image_var(ds: xr.Dataset) -> str:
    """The single image data variable (name comes from the NGFF image, not hardcoded)."""
    return next(iter(ds.data_vars))


@pytest.mark.slow
def test_open_dataset_from_idr() -> None:
    """open_ngff_dataset on real IDR data: shape, dims, and the verbatim ome carrier."""
    ds = open_ngff_dataset(IDR_SAMPLE_URL)

    var = _image_var(ds)
    assert ds[var].shape == (2, 236, 275, 271)
    assert list(ds.sizes) == ["c", "z", "y", "x"]

    # New contract: the verbatim NGFF `ome` block rides on attrs as the carrier.
    assert "ome" in ds.attrs
    assert "multiscales" in ds.attrs["ome"]


@pytest.mark.slow
def test_open_datatree_from_idr() -> None:
    """open_ngff_datatree on real IDR data: level-index nodes + carrier on the root."""
    dt = open_ngff_datatree(IDR_SAMPLE_URL)

    assert set(dt.children.keys()) == {"0", "1", "2"}

    assert dt["0"].ds[_image_var(dt["0"].ds)].shape == (2, 236, 275, 271)
    assert dt["1"].ds[_image_var(dt["1"].ds)].shape == (2, 236, 137, 135)
    assert dt["2"].ds[_image_var(dt["2"].ds)].shape == (2, 236, 68, 67)

    # Carrier on the root holds the verbatim multiscales metadata.
    assert "ome" in dt.attrs
    ms = dt.attrs["ome"]["multiscales"][0]
    assert ms["version"] == "0.4"
    assert len(ms["axes"]) == 4


@pytest.mark.slow
def test_backend_with_idr_dataset() -> None:
    """Backend (engine='ome-zarr') opens real IDR data as a single-level Dataset."""
    ds = xr.open_dataset(IDR_SAMPLE_URL, engine="ome-zarr")

    var = _image_var(ds)
    assert ds[var].shape == (2, 236, 275, 271)
    assert list(ds.sizes) == ["c", "z", "y", "x"]


@pytest.mark.slow
def test_backend_with_idr_datatree() -> None:
    """Backend (engine='ome-zarr') opens real IDR data as a level-indexed DataTree."""
    dt = xr.open_datatree(IDR_SAMPLE_URL, engine="ome-zarr")

    assert set(dt.children.keys()) == {"0", "1", "2"}
    assert dt["0"].ds[_image_var(dt["0"].ds)].shape == (2, 236, 275, 271)


@pytest.mark.slow
def test_idr_data_coordinates() -> None:
    """Physical spatial coords are lazy transform-backed; channels come from omero."""
    ds = open_ngff_dataset(IDR_SAMPLE_URL)

    # Spatial axes carry lazy, transform-backed physical coordinates with CF units.
    for axis, size in (("z", 236), ("y", 275), ("x", 271)):
        assert axis in ds.coords
        assert isinstance(ds.xindexes[axis], TransformIndex)
        assert len(ds.coords[axis]) == size
        assert ds[axis].attrs.get("units") == "micrometer"

    # omero channel labels are mapped onto the `c` coordinate and match the carrier.
    assert "c" in ds.coords
    assert len(ds.coords["c"]) == 2
    omero_labels = [ch["label"] for ch in ds.attrs["ome"]["omero"]["channels"]]
    assert list(ds.coords["c"].values) == omero_labels


@pytest.mark.slow
def test_idr_lazy_loading() -> None:
    """Data is lazy-loaded (dask) and not fetched until compute."""
    import dask.array as da

    ds = xr.open_dataset(IDR_SAMPLE_URL, engine="ome-zarr")
    var = _image_var(ds)

    assert isinstance(ds[var].data, da.Array)

    subset = ds[var].isel(c=0, z=0)
    assert isinstance(subset.data, da.Array)

    computed = subset.compute()
    assert computed.shape == (275, 271)
