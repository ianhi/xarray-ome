"""Coverage for the validated *synthesis* reader contract.

These tests exercise behaviour the old strawman lacked:

- spatial coords are lazy, transform-backed (``TransformIndex``) rather than
  materialized ndarrays;
- ergonomic ``.sel`` with plain scalars and label slices;
- omero channel labels mapped onto the ``c`` coordinate, with a graceful
  integer fallback when no omero block is present;
- CF ``units`` + ``axis_type`` coord attrs;
- the verbatim ``ome`` carrier on the DataTree root, faithfully preserving the
  ``coordinateTransformations``.

The fixtures synthesise tiny 0.5 stores in ``tmp_path`` via ngff-zarr so the
tests never depend on gitignored scratch data under ``experiments/data/``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pytest
from ngff_zarr import (  # type: ignore[import-untyped]
    Omero,
    OmeroChannel,
    OmeroWindow,
    to_multiscales,
    to_ngff_image,
    to_ngff_zarr,
)

from xarray_ngff import open_ngff_dataset, open_ngff_datatree
from xarray_ngff.indexes import TransformIndex

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path


def _write_store(
    path: str,
    *,
    with_omero: bool,
    scale_factors: list[int],
) -> None:
    """Write a tiny (c, y, x) multiscale 0.5 store with nonzero translation/units."""
    data = np.arange(2 * 8 * 8, dtype=np.uint8).reshape(2, 8, 8)
    image = to_ngff_image(
        data,
        dims=["c", "y", "x"],
        scale={"c": 1.0, "y": 0.5, "x": 0.5},
        # Nonzero translation so coord origin != 0 (exercises the affine offset).
        translation={"c": 0.0, "y": 10.0, "x": -5.0},
        name="img",
        axes_units={"y": "micrometer", "x": "micrometer"},
    )
    multiscales = to_multiscales(image, scale_factors=scale_factors)
    if with_omero:
        window = OmeroWindow(min=0, max=255, start=0, end=255)
        multiscales.metadata.omero = Omero(
            channels=[
                OmeroChannel(color="FF0000", window=window, label="DAPI"),
                OmeroChannel(color="00FF00", window=window, label="GFP"),
            ]
        )
    to_ngff_zarr(path, multiscales)


@pytest.fixture
def omero_store(tmp_path: Path) -> Generator[str, None, None]:
    """Multiscale (2 levels) store WITH an omero block, nonzero translation, units."""
    p = str(tmp_path / "omero.ome.zarr")
    _write_store(p, with_omero=True, scale_factors=[2])
    yield p


@pytest.fixture
def no_omero_store(tmp_path: Path) -> Generator[str, None, None]:
    """Multiscale (2 levels) store WITHOUT an omero block (integer-c fallback)."""
    p = str(tmp_path / "plain.ome.zarr")
    _write_store(p, with_omero=False, scale_factors=[2])
    yield p


def test_spatial_coords_are_lazy_affine(omero_store: str) -> None:
    """Spatial coords are backed by TransformIndex, not a materialized ndarray."""
    ds = open_ngff_dataset(omero_store)

    for axis in ("y", "x"):
        assert isinstance(ds.xindexes[axis], TransformIndex)

    # Values are computed lazily from (scale, translation); nonzero origin shows
    # the translation is honoured. y: scale=0.5, translation=10.0.
    np.testing.assert_allclose(ds.coords["y"].values[:2], [10.0, 10.5])
    # x: scale=0.5, translation=-5.0.
    np.testing.assert_allclose(ds.coords["x"].values[:2], [-5.0, -4.5])


def test_sel_scalar_and_label_slice(omero_store: str) -> None:
    """Ergonomic .sel: plain scalar (nearest default) and a physical label slice."""
    ds = open_ngff_dataset(omero_store)

    # Plain scalar -> nearest pixel. y origin 10.0, step 0.5 => 10.7 -> idx 1 (10.5).
    picked = ds.sel(y=10.7)
    np.testing.assert_allclose(float(picked.coords["y"].values), 10.5)

    # Label slice over a physical interval selects the enclosed pixels.
    sub = ds.sel(y=slice(10.0, 11.0))
    assert sub.sizes["y"] >= 2
    assert float(sub.coords["y"].values[0]) == pytest.approx(10.0)


def test_omero_channel_labels_on_c(omero_store: str) -> None:
    """omero channel labels are mapped onto the `c` coordinate."""
    ds = open_ngff_dataset(omero_store)
    assert "c" in ds.coords
    assert list(ds.coords["c"].values) == ["DAPI", "GFP"]
    assert ds["c"].attrs.get("axis_type") == "channel"


def test_integer_c_fallback_without_omero(no_omero_store: str) -> None:
    """No omero block => no `c` label coordinate (graceful integer fallback)."""
    ds = open_ngff_dataset(no_omero_store)
    assert "c" not in ds.coords
    assert "c" in ds.dims
    # Spatial coords are unaffected.
    assert isinstance(ds.xindexes["y"], TransformIndex)


def test_cf_units_and_axis_type_attrs(omero_store: str) -> None:
    """CF `units` and NGFF `axis_type` ride as coord attrs on spatial axes."""
    ds = open_ngff_dataset(omero_store)
    for axis in ("y", "x"):
        assert ds[axis].attrs["units"] == "micrometer"
        assert ds[axis].attrs["axis_type"] == "space"


def test_ome_carrier_on_root_with_transforms(omero_store: str) -> None:
    """The verbatim `ome` carrier sits on the DataTree root and keeps transforms."""
    dt = open_ngff_datatree(omero_store)

    # Level nodes named by index; root carries the verbatim block, no data var.
    assert set(dt.children) == {"0", "1"}
    assert len(dt.ds.data_vars) == 0
    assert "ome" in dt.attrs

    ome = dt.attrs["ome"]
    multiscales = ome["multiscales"]
    datasets = multiscales[0]["datasets"]
    assert len(datasets) == 2  # two pyramid levels

    # The level-0 coordinateTransformations faithfully carry scale + translation.
    cts = datasets[0]["coordinateTransformations"]
    scales = [t["scale"] for t in cts if t["type"] == "scale"]
    translations = [t["translation"] for t in cts if t["type"] == "translation"]
    assert scales == [[1.0, 0.5, 0.5]]
    assert translations == [[0.0, 10.0, -5.0]]

    # omero block survives verbatim on the carrier.
    assert ome["omero"]["channels"][0]["label"] == "DAPI"
