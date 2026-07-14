"""The ``.ngff`` accessor: typed reads, role lookup, and builders.

Objects are synthesised via ngff-zarr and opened through the real reader, so the
tests exercise the accessor against genuine Dataset / DataTree instances (with
transform-backed coords and the verbatim ``ome`` carrier).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pytest
import xarray as xr
from ngff_zarr import (  # type: ignore[import-untyped]
    to_multiscales,
    to_ngff_image,
    to_ngff_zarr,
)

import xarray_ngff  # noqa: F401  (activates the .ngff accessor)
from xarray_ngff import (
    AxisInfo,
    ChannelInfo,
    open_ngff_dataset,
    open_ngff_datatree,
    write_ngff_dataset,
)

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path


def _write_calibrated(path: str, *, scale_factors: list[int]) -> None:
    """A calibrated (c, y, x) store: nonzero translation + units on y/x."""
    data = np.arange(2 * 16 * 16, dtype=np.uint8).reshape(2, 16, 16)
    image = to_ngff_image(
        data,
        dims=["c", "y", "x"],
        scale={"c": 1.0, "y": 0.5, "x": 0.5},
        translation={"c": 0.0, "y": 10.0, "x": -5.0},
        name="img",
        axes_units={"y": "micrometer", "x": "micrometer"},
    )
    to_ngff_zarr(path, to_multiscales(image, scale_factors=scale_factors))


def _write_unitless(path: str) -> None:
    """A (y, x) store that declares no units (uncalibrated / pixel case)."""
    data = np.arange(8 * 8, dtype=np.float32).reshape(8, 8)
    image = to_ngff_image(
        data,
        dims=["y", "x"],
        scale={"y": 2.0, "x": 2.0},
        translation={"y": 0.0, "x": 0.0},
        name="plain",
    )
    to_ngff_zarr(path, to_multiscales(image, scale_factors=[]))


@pytest.fixture
def calibrated_store(tmp_path: Path) -> Generator[str, None, None]:
    p = str(tmp_path / "calibrated.ome.zarr")
    _write_calibrated(p, scale_factors=[])
    yield p


@pytest.fixture
def calibrated_pyramid(tmp_path: Path) -> Generator[str, None, None]:
    p = str(tmp_path / "pyramid.ome.zarr")
    _write_calibrated(p, scale_factors=[2, 4])
    yield p


@pytest.fixture
def unitless_store(tmp_path: Path) -> Generator[str, None, None]:
    p = str(tmp_path / "unitless.ome.zarr")
    _write_unitless(p)
    yield p


# ---- reads ---------------------------------------------------------------
def test_version_name_axes(calibrated_store: str) -> None:
    ds = open_ngff_dataset(calibrated_store)
    assert isinstance(ds.ngff.version, str) and ds.ngff.version  # e.g. "0.4"/"0.5"
    axes = ds.ngff.axes
    assert [a.name for a in axes] == ["c", "y", "x"]
    assert all(isinstance(a, AxisInfo) for a in axes)
    # y/x are declared "space"; c is "channel".
    types = {a.name: a.type for a in axes}
    assert types["y"] == "space" and types["x"] == "space"


def test_units_read_from_coords(calibrated_store: str) -> None:
    ds = open_ngff_dataset(calibrated_store)
    units = ds.ngff.units
    assert units["y"] == "micrometer"
    assert units["x"] == "micrometer"
    # c has no declared unit.
    assert units["c"] is None


def test_calibrated_signal(calibrated_store: str, unitless_store: str) -> None:
    cal = open_ngff_dataset(calibrated_store).ngff.calibrated
    assert cal["y"] is True and cal["x"] is True  # declared units
    assert cal["c"] is False  # no coord unit

    uncal = open_ngff_dataset(unitless_store).ngff.calibrated
    assert uncal["y"] is False and uncal["x"] is False  # pixel / uncalibrated


def test_channels_present_and_absent(calibrated_store: str, tmp_path: Path) -> None:
    # The plain calibrated store has no omero block -> channels is None.
    ds_no_omero = open_ngff_dataset(calibrated_store)
    assert ds_no_omero.ngff.channels is None

    # Inject an omero block into the carrier and confirm typed reads.
    ds = open_ngff_dataset(calibrated_store)
    ds.attrs["ome"]["omero"] = {
        "channels": [
            {"label": "DAPI", "color": "0000FF", "window": {"min": 0, "max": 255}},
            {"label": "GFP"},
        ]
    }
    channels = ds.ngff.channels
    assert channels is not None
    assert [c.label for c in channels] == ["DAPI", "GFP"]
    assert all(isinstance(c, ChannelInfo) for c in channels)
    assert channels[0].color == "0000FF"
    assert channels[0].window == {"min": 0, "max": 255}
    assert channels[1].color is None and channels[1].window is None


def test_raw_returns_carrier(calibrated_store: str) -> None:
    ds = open_ngff_dataset(calibrated_store)
    raw = ds.ngff.raw
    assert isinstance(raw, dict)
    assert "multiscales" in raw
    # Defensive: an object with no carrier returns {} (never KeyError).
    assert xr.Dataset().ngff.raw == {}


def test_coord_role_lookup(calibrated_store: str) -> None:
    ds = open_ngff_dataset(calibrated_store)
    assert ds.ngff.coord_name("x", kind="world") == "x"
    assert ds.ngff.coord_name("x", kind="pixel") is None
    wc = ds.ngff.world_coord("x")
    assert wc is not None
    np.testing.assert_allclose(wc.values[0], -5.0)
    assert ds.ngff.pixel_coord("x") is None


# ---- coordinate-reconstructed axes (carrier absent) ----------------------
def test_axes_reconstructed_from_coords_without_carrier() -> None:
    """A Dataset with physical coords + attrs but NO ``ome`` carrier still
    reports axes / units / calibrated, reconstructed from the coordinates."""
    ds = xr.Dataset({"image": (("y", "x"), np.zeros((4, 8), dtype=np.float32))})
    ds = ds.assign_coords(
        y=("y", np.arange(4) * 0.5 + 2.0),
        x=("x", np.arange(8) * 0.25),
    )
    ds["y"].attrs.update(units="micrometer", axis_type="space")
    ds["x"].attrs.update(units="micrometer", axis_type="space")
    assert "ome" not in ds.attrs

    axes = ds.ngff.axes
    assert [a.name for a in axes] == ["y", "x"]
    assert [a.type for a in axes] == ["space", "space"]
    assert ds.ngff.units == {"y": "micrometer", "x": "micrometer"}
    assert ds.ngff.calibrated == {"y": True, "x": True}
    # version / name / channels are honestly absent without a carrier.
    assert ds.ngff.version is None
    assert ds.ngff.channels is None
    # scale / translation reconstructed from the dense coords (first two values).
    assert ds.ngff.scale == pytest.approx({"y": 0.5, "x": 0.25})
    assert ds.ngff.translation == pytest.approx({"y": 2.0, "x": 0.0})


def test_axis_type_inferred_from_name_without_attrs() -> None:
    """When a coord carries no ``axis_type`` attr, the type is inferred from the
    dimension name (x/y/z -> space, t -> time, c -> channel)."""
    ds = xr.Dataset({"image": (("t", "z", "y", "x"), np.zeros((1, 1, 2, 2)))})
    types = {a.name: a.type for a in ds.ngff.axes}
    assert types == {"t": "time", "z": "space", "y": "space", "x": "space"}


def test_dataarray_accessor_reads_from_coords(calibrated_store: str) -> None:
    """``ds["image"].ngff`` (a DataArray, whose attrs drop the carrier) still
    reconstructs axes / units / calibrated / transforms from its coordinates."""
    ds = open_ngff_dataset(calibrated_store)
    var = next(iter(ds.data_vars))
    da = ds[var]
    # DataArray attrs do NOT carry the parent's ``ome`` block.
    assert "ome" not in da.attrs
    assert da.ngff.version is None and da.ngff.channels is None
    assert [a.name for a in da.ngff.axes] == ["c", "y", "x"]
    assert da.ngff.units["y"] == "micrometer"
    assert da.ngff.calibrated["y"] is True
    # transform-index-backed coords report exact scale/translation.
    assert da.ngff.scale["x"] == pytest.approx(0.5)
    assert da.ngff.translation["x"] == pytest.approx(-5.0)
    # repr renders (axes present, no carrier).
    assert "DataArray.ngff" in repr(da.ngff)
    assert "transform" in da.ngff._repr_html_()


def test_scale_translation_from_transform_index(calibrated_store: str) -> None:
    ds = open_ngff_dataset(calibrated_store)
    assert ds.ngff.scale == pytest.approx({"y": 0.5, "x": 0.5})
    assert ds.ngff.translation == pytest.approx({"y": 10.0, "x": -5.0})
    # channel ``c`` has no real coordinate -> excluded from the transforms.
    assert "c" not in ds.ngff.scale


# ---- DataTree ------------------------------------------------------------
def test_datatree_levels_and_navigation(calibrated_pyramid: str) -> None:
    dt = open_ngff_datatree(calibrated_pyramid)
    assert dt.ngff.levels == ["0", "1", "2"]
    assert dt.ngff.n_levels == 3
    # Finest is level 0 (16 px on x), coarsest is level 2 (4 px).
    assert dt.ngff.finest.dataset.sizes["x"] == 16
    assert dt.ngff.coarsest.dataset.sizes["x"] == 4
    assert dt.ngff.level(1).dataset.sizes["x"] == 8


def test_coarsest_at_least(calibrated_pyramid: str) -> None:
    dt = open_ngff_datatree(calibrated_pyramid)
    # Levels have x sizes 16, 8, 4. Coarsest with x >= 8 is level 1 (8 px).
    assert dt.ngff.coarsest_at_least(8, dim="x").dataset.sizes["x"] == 8
    # Nothing >= 100 -> fall back to the finest.
    assert dt.ngff.coarsest_at_least(100, dim="x").dataset.sizes["x"] == 16
    # >= 4 qualifies at the coarsest.
    assert dt.ngff.coarsest_at_least(4, dim="x").dataset.sizes["x"] == 4


def test_datatree_reads_root_carrier(calibrated_pyramid: str) -> None:
    dt = open_ngff_datatree(calibrated_pyramid)
    assert isinstance(dt.ngff.version, str)
    assert [a.name for a in dt.ngff.axes] == ["c", "y", "x"]
    # units/calibrated resolve against the finest level's coords.
    assert dt.ngff.units["x"] == "micrometer"
    assert dt.ngff.calibrated["x"] is True


# ---- builders ------------------------------------------------------------
def test_set_scale_does_not_mutate_and_reindexes(calibrated_store: str) -> None:
    ds = open_ngff_dataset(calibrated_store)
    x0 = float(ds.coords["x"].values[1] - ds.coords["x"].values[0])
    assert x0 == pytest.approx(0.5)  # original scale

    ds2 = ds.ngff.set_scale(x=6.0)
    # Original is untouched.
    assert float(ds.coords["x"].values[1] - ds.coords["x"].values[0]) == pytest.approx(0.5)
    # New object has the new scale; translation preserved.
    assert float(ds2.coords["x"].values[1] - ds2.coords["x"].values[0]) == pytest.approx(6.0)
    np.testing.assert_allclose(ds2.coords["x"].values[0], -5.0)

    # World .sel hits the expected pixel: x = 6*i - 5 -> world 7.0 => i = 2.
    picked = ds2.sel(x=7.0)
    np.testing.assert_allclose(float(picked.coords["x"].values), 7.0)


def test_set_units_shows_on_accessor(unitless_store: str) -> None:
    ds = open_ngff_dataset(unitless_store)
    assert ds.ngff.units["x"] is None  # uncalibrated to start
    ds2 = ds.ngff.set_units(x="micrometer")
    assert ds2.ngff.units["x"] == "micrometer"
    assert ds2.ngff.calibrated["x"] is True
    # Original untouched.
    assert ds.ngff.units["x"] is None


def test_set_scale_roundtrips_through_writer(calibrated_store: str, tmp_path: Path) -> None:
    """The coord-driven set_scale must survive a write + reopen.

    The writer derives scale/translation from the coords (coord[1]-coord[0]),
    so a coord-updating builder is expected to round-trip. If this fails, it
    signals the writer is NOT coord-driven -- report it rather than hacking.
    """
    ds = open_ngff_dataset(calibrated_store)
    ds2 = ds.ngff.set_scale(x=6.0, y=6.0)

    out = str(tmp_path / "roundtrip.ome.zarr")
    write_ngff_dataset(ds2, out)
    reopened = open_ngff_dataset(out)

    new_x = float(reopened.coords["x"].values[1] - reopened.coords["x"].values[0])
    new_y = float(reopened.coords["y"].values[1] - reopened.coords["y"].values[0])
    assert new_x == pytest.approx(6.0), "set_scale did NOT round-trip through writer"
    assert new_y == pytest.approx(6.0)
    # Units survived too.
    assert reopened.ngff.units["x"] == "micrometer"


def test_crop_world_range(calibrated_store: str) -> None:
    ds = open_ngff_dataset(calibrated_store)
    # x world runs -5.0, -4.5, ... (step 0.5). Crop [-5.0, -3.0] => ~5 pixels.
    cropped = ds.ngff.crop(x=(-5.0, -3.0))
    assert cropped.sizes["x"] < ds.sizes["x"]
    np.testing.assert_allclose(cropped.coords["x"].values[0], -5.0)
    assert float(cropped.coords["x"].values[-1]) <= -3.0 + 1e-9
    # Original untouched.
    assert ds.sizes["x"] == 16
