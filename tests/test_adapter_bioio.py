"""Integration tests for the bioio -> xarray-ngff adapter (live IDR, network).

The adapter (`xarray_ngff.adapters.bioio`) recovers the verbatim ``ome`` block
bioio preserves on ``xarray_dask_data.attrs['unprocessed']`` and rebuilds *our*
representation from it. The acceptance bar is equality with the reader
(``open_ngff_dataset`` / ``open_ngff_datatree``) on the same store.

Both ``bioio`` and ``bioio-ome-zarr`` are optional extras (`xarray-ngff[bioio]`),
so these are skipped unless both are installed; they also hit the network, so they
carry the ``slow`` marker like the other IDR tests.
"""

import numpy as np
import pytest

from xarray_ngff import open_ngff_dataset, open_ngff_datatree

pytest.importorskip("bioio")
pytest.importorskip("bioio_ome_zarr")

from bioio import BioImage  # noqa: E402

from xarray_ngff.adapters.bioio import from_bioio, from_bioio_datatree  # noqa: E402

# NGFF 0.5 store: a 2-D (y, x) micrometer-calibrated image whose omero block
# declares a "Cy3" channel but which has *no* c axis (the omero-without-c edge
# case). bioio flattens it to (T:1, C:1, Z:1, Y:8978, X:6510) and drops the units.
# NOTE: no trailing slash (bioio-ome-zarr is picky about it).
IDR_URL = "https://livingobjects.ebi.ac.uk/idr/zarr/v0.5/idr0066/ExpD_chicken_embryo_MIP.ome.zarr"


@pytest.mark.slow
def test_from_bioio_matches_open_ngff_dataset() -> None:
    """`from_bioio` reconstructs exactly what `open_ngff_dataset` produces."""
    got = from_bioio(BioImage(IDR_URL))
    ref = open_ngff_dataset(IDR_URL)

    # The three invented size-1 axes (T/C/Z) are dropped; only the real (y, x) remain.
    assert dict(got.sizes) == dict(ref.sizes) == {"y": 8978, "x": 6510}
    assert list(got.data_vars) == list(ref.data_vars)

    # Physical coordinates, units, and axis_type recovered from the ome block.
    for axis in ("y", "x"):
        np.testing.assert_allclose(got[axis].values, ref[axis].values)
        assert got[axis].attrs == ref[axis].attrs
    assert got.ngff.units == ref.ngff.units == {"y": "micrometer", "x": "micrometer"}

    # omero channel surfaced from the carrier even though there is no c dim.
    assert [c.label for c in got.ngff.channels] == ["Cy3"]

    # Lossless carrier + laziness preserved; only a small crop is materialised.
    assert got.attrs["ome"] == ref.attrs["ome"]
    var = next(iter(got.data_vars))
    assert got[var].chunks is not None  # still lazy (dask-backed)
    crop = {"y": slice(0, 4), "x": slice(0, 4)}
    np.testing.assert_array_equal(got[var].isel(crop).values, ref[var].isel(crop).values)


@pytest.mark.slow
def test_from_bioio_selects_resolution_level() -> None:
    """A non-zero `resolution` rebuilds the matching coarser level."""
    got = from_bioio(BioImage(IDR_URL), resolution=1)
    ref = open_ngff_dataset(IDR_URL, resolution=1)

    assert dict(got.sizes) == dict(ref.sizes) == {"y": 4489, "x": 3255}
    # Level-1 scale is 3.2 um (level-0 * 2), read from that level's transform.
    np.testing.assert_allclose(got["y"].values[:3], [0.0, 3.2, 6.4])
    np.testing.assert_allclose(got["y"].values, ref["y"].values)


@pytest.mark.slow
def test_from_bioio_datatree_matches_open_ngff_datatree() -> None:
    """`from_bioio_datatree` reconstructs every level like `open_ngff_datatree`."""
    got = from_bioio_datatree(BioImage(IDR_URL))
    ref = open_ngff_datatree(IDR_URL)

    # Same level-index nodes ("0".."6") as the reader.
    assert set(got.children) == set(ref.children)

    for name in ref.children:
        assert dict(got[name].ds.sizes) == dict(ref[name].ds.sizes)
        np.testing.assert_allclose(got[name].ds["y"].values, ref[name].ds["y"].values)

    # Verbatim carrier on the root only (matches the reader).
    assert got.attrs["ome"] == ref.attrs["ome"]


@pytest.mark.slow
def test_from_bioio_accepts_bare_dataarray() -> None:
    """The DataArray form works for level 0 and rejects a coarser request."""
    xd = BioImage(IDR_URL).xarray_dask_data
    got = from_bioio(xd)
    assert dict(got.sizes) == {"y": 8978, "x": 6510}

    with pytest.raises(ValueError, match="bare DataArray"):
        from_bioio(xd, resolution=1)
