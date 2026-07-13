"""Reader coordinate construction via ``transform_coords`` / ``TransformIndex``.

Focused coverage for the migration of ``_build_level_dataset`` onto the unified
``transform_coords`` builder:

- a *calibrated* store yields world coordinates whose ``.sel`` works in world
  units and whose declared ``units`` ride as CF coord attrs;
- *honest units*: a store that omits the NGFF unit yields a coordinate with NO
  ``units`` attr (never fabricated), and the pure identity path (no
  scale/translation) yields plain integer-pixel coordinates;
- a multiscale *DataTree* opens with per-level coordinates whose ``.sel`` returns
  the correct (per-level different) number of pixels;
- the verbatim ``ome`` carrier is preserved on the root / attrs.

Stores are synthesised in ``tmp_path`` via ngff-zarr so the tests never depend
on scratch data.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pytest
from ngff_zarr import (  # type: ignore[import-untyped]
    to_multiscales,
    to_ngff_image,
    to_ngff_zarr,
)

from xarray_ngff import open_ngff_dataset, open_ngff_datatree
from xarray_ngff.indexes import TransformIndex, transform_coords

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path


def _write_calibrated(path: str, *, scale_factors: list[int]) -> None:
    """A calibrated (c, y, x) store: nonzero translation + declared units on y/x."""
    data = np.arange(2 * 16 * 16, dtype=np.uint8).reshape(2, 16, 16)
    image = to_ngff_image(
        data,
        dims=["c", "y", "x"],
        scale={"c": 1.0, "y": 0.5, "x": 0.5},
        translation={"c": 0.0, "y": 10.0, "x": -5.0},
        name="img",
        axes_units={"y": "micrometer", "x": "micrometer"},
    )
    multiscales = to_multiscales(image, scale_factors=scale_factors)
    to_ngff_zarr(path, multiscales)


@pytest.fixture
def calibrated_store(tmp_path: Path) -> Generator[str, None, None]:
    """Single-level calibrated store with world coords + declared units."""
    p = str(tmp_path / "calibrated.ome.zarr")
    _write_calibrated(p, scale_factors=[])
    yield p


@pytest.fixture
def calibrated_pyramid(tmp_path: Path) -> Generator[str, None, None]:
    """Two-level calibrated pyramid (scale_factors=[2])."""
    p = str(tmp_path / "pyramid.ome.zarr")
    _write_calibrated(p, scale_factors=[2])
    yield p


def _write_unitless(path: str) -> None:
    """A (y, x) store that OMITS axes_units entirely (honest no-unit case)."""
    data = np.arange(8 * 8, dtype=np.float32).reshape(8, 8)
    image = to_ngff_image(
        data,
        dims=["y", "x"],
        scale={"y": 2.0, "x": 2.0},
        translation={"y": 0.0, "x": 0.0},
        name="plain",
        # No axes_units -> the store declares no unit on any axis.
    )
    multiscales = to_multiscales(image, scale_factors=[])
    to_ngff_zarr(path, multiscales)


@pytest.fixture
def unitless_store(tmp_path: Path) -> Generator[str, None, None]:
    """Store whose axes declare no unit -> coords must have no ``units`` attr."""
    p = str(tmp_path / "unitless.ome.zarr")
    _write_unitless(p)
    yield p


def test_calibrated_world_coords_and_sel(calibrated_store: str) -> None:
    """Opening a calibrated store yields world coords backed by TransformIndex."""
    ds = open_ngff_dataset(calibrated_store)

    for axis in ("y", "x"):
        assert isinstance(ds.xindexes[axis], TransformIndex)

    # World values: y = 0.5 * i + 10.0, x = 0.5 * i - 5.0.
    np.testing.assert_allclose(ds.coords["y"].values[:3], [10.0, 10.5, 11.0])
    np.testing.assert_allclose(ds.coords["x"].values[:3], [-5.0, -4.5, -4.0])


def test_calibrated_sel_in_world_units(calibrated_store: str) -> None:
    """.sel works in world units: scalar (nearest) and inclusive label slice."""
    ds = open_ngff_dataset(calibrated_store)

    # Nearest pixel: y origin 10.0, step 0.5 => 10.7 -> idx 1 (10.5).
    picked = ds.sel(y=10.7)
    np.testing.assert_allclose(float(picked.coords["y"].values), 10.5)

    # World-unit interval selects the enclosed pixels.
    sub = ds.sel(y=slice(10.0, 11.0))
    assert sub.sizes["y"] >= 3
    np.testing.assert_allclose(float(sub.coords["y"].values[0]), 10.0)


def test_declared_units_present(calibrated_store: str) -> None:
    """Declared NGFF units ride onto the coords as CF ``units`` attrs."""
    ds = open_ngff_dataset(calibrated_store)
    for axis in ("y", "x"):
        assert ds[axis].attrs["units"] == "micrometer"
        assert ds[axis].attrs["axis_type"] == "space"


def test_honest_units_absent_when_store_omits(unitless_store: str) -> None:
    """A store that declares no unit must NOT fabricate a ``units`` coord attr."""
    ds = open_ngff_dataset(unitless_store)
    for axis in ("y", "x"):
        # Coord still exists and is transform-backed (scale=2.0 here).
        assert isinstance(ds.xindexes[axis], TransformIndex)
        assert "units" not in ds[axis].attrs


def test_identity_fallback_yields_pixel_coords() -> None:
    """The pure identity path (no scale/translate) yields integer pixel coords.

    This exercises the "no world transform" fallback directly through
    ``transform_coords`` (the branch ``_build_level_dataset`` hits when a store
    omits scale/translation). ngff-zarr always materialises a scale/translation,
    so this direct check documents that the identity path yields honest pixel
    coordinates with no units attached.
    """
    coords = transform_coords({"y": 5, "x": 4})
    assert isinstance(coords.xindexes["y"], TransformIndex)
    np.testing.assert_array_equal(coords["y"].values, np.arange(5))
    np.testing.assert_array_equal(coords["x"].values, np.arange(4))
    # No units are ever attached by the builder itself.
    assert "units" not in coords["y"].attrs
    assert "units" not in coords["x"].attrs


def test_multiscale_datatree_per_level_coords(calibrated_pyramid: str) -> None:
    """A pyramid opens with per-level coords; .sel returns per-level pixel counts."""
    dt = open_ngff_datatree(calibrated_pyramid)

    assert set(dt.children) == {"0", "1"}

    l0 = dt["0"].ds
    l1 = dt["1"].ds

    # Both levels carry lazy world coords on y/x.
    for ds in (l0, l1):
        for axis in ("y", "x"):
            assert isinstance(ds.xindexes[axis], TransformIndex)

    # Level 0 is 16 px @ step 0.5; level 1 is 8 px @ step 1.0 (downsampled x2).
    assert l0.sizes["x"] == 16
    assert l1.sizes["x"] == 8

    # The same world-unit slice selects DIFFERENT pixel counts per level because
    # the levels have different resolutions -- the coords are genuinely per-level.
    world = slice(-5.0, 0.0)  # x world interval spanning ~5 um from the origin
    n0 = l0.sel(x=world).sizes["x"]
    n1 = l1.sel(x=world).sizes["x"]
    assert n0 > n1
    # ~5 um at 0.5 um/px ~= 11 px; at 1.0 um/px ~= 6 px.
    assert n0 == pytest.approx(11, abs=1)
    assert n1 == pytest.approx(6, abs=1)


def test_ome_carrier_preserved_on_root(calibrated_pyramid: str) -> None:
    """The verbatim ``ome`` carrier survives on the DataTree root attrs."""
    dt = open_ngff_datatree(calibrated_pyramid)

    assert "ome" in dt.attrs
    assert len(dt.ds.data_vars) == 0
    datasets = dt.attrs["ome"]["multiscales"][0]["datasets"]
    assert len(datasets) == 2

    # And on a single-level Dataset the carrier rides on ds.attrs.
    ds = open_ngff_dataset(calibrated_pyramid)
    assert "ome" in ds.attrs
    assert "multiscales" in ds.attrs["ome"]
