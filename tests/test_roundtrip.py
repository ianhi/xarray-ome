"""Lossless round-trip coverage for the writer (core rules 7 and 8).

Exercises two gaps found by round-tripping the reader's own output:

- Fix 1: ``coords_to_transforms`` must SKIP non-numeric coordinates (the
  object/string channel-label ``c`` coord the reader adds from omero) instead of
  trying ``float(coord[1] - coord[0])`` and raising ``TypeError``.
- Fix 2: the writer must re-emit the verbatim ``ome`` carrier -- deep-merged with
  the freshly written managed ``multiscales`` -- so ``omero`` and any unknown /
  future fields survive a write, while managed transform/axis edits win.

Stores are synthesised in ``tmp_path`` via ngff-zarr and (for omero) by writing
the omero block directly into the store's group ``zarr.json``, matching how a
real OME-Zarr store on disk carries channels.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import numpy as np
import pytest
import xarray as xr
from ngff_zarr import (  # type: ignore[import-untyped]
    to_multiscales,
    to_ngff_image,
    to_ngff_zarr,
)

from xarray_ngff import (
    open_ngff_dataset,
    open_ngff_datatree,
    write_ngff_dataset,
    write_ngff_datatree,
)
from xarray_ngff.writer import deep_merge

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path


def _inject_ome(path: str, extra: dict) -> None:
    """Deep-merge ``extra`` into the store's group ``zarr.json`` ``attributes.ome``."""
    from pathlib import Path as _Path

    zarr_json = _Path(path) / "zarr.json"
    meta = json.loads(zarr_json.read_text())
    ome = meta["attributes"].get("ome", {})
    meta["attributes"]["ome"] = deep_merge(ome, extra)
    zarr_json.write_text(json.dumps(meta))


def _write_channel_store(path: str) -> None:
    """A (c, y, x) store with an omero channels block written into zarr.json."""
    data = np.arange(2 * 16 * 16, dtype=np.uint8).reshape(2, 16, 16)
    image = to_ngff_image(
        data,
        dims=["c", "y", "x"],
        scale={"c": 1.0, "y": 0.5, "x": 0.5},
        translation={"c": 0.0, "y": 10.0, "x": -5.0},
        name="img",
        axes_units={"y": "micrometer", "x": "micrometer"},
    )
    to_ngff_zarr(path, to_multiscales(image, scale_factors=[2]))
    _inject_ome(
        path,
        {
            "omero": {
                "channels": [
                    {
                        "label": "DAPI",
                        "color": "0000FF",
                        "window": {"min": 0, "max": 255},
                    },
                    {"label": "GFP", "color": "00FF00"},
                ]
            }
        },
    )


@pytest.fixture
def channel_store(tmp_path: Path) -> Generator[str, None, None]:
    p = str(tmp_path / "channels.ome.zarr")
    _write_channel_store(p)
    yield p


def test_channels_roundtrip_datatree(channel_store: str, tmp_path: Path) -> None:
    """Write a channel store as a DataTree (Fix 1: no crash) and preserve labels (Fix 2)."""
    dt = open_ngff_datatree(channel_store)
    # Reader adds an object-dtype string `c` coord from omero.
    assert dt["0"].ds["c"].dtype == object

    out = str(tmp_path / "roundtrip_channels.ome.zarr")
    write_ngff_datatree(dt, out)  # must NOT raise (covers Fix 1)

    dt2 = open_ngff_datatree(out)
    channels = dt2.ngff.channels
    assert channels is not None
    assert [c.label for c in channels] == ["DAPI", "GFP"]
    assert channels[0].color == "0000FF"
    assert channels[0].window == {"min": 0, "max": 255}


def test_channels_roundtrip_dataset(channel_store: str, tmp_path: Path) -> None:
    """Same, for the single-Dataset write path."""
    ds = open_ngff_dataset(channel_store)
    assert ds["c"].dtype == object

    out = str(tmp_path / "roundtrip_channels_ds.ome.zarr")
    write_ngff_dataset(ds, out)  # must NOT raise (covers Fix 1)

    ds2 = open_ngff_dataset(out)
    channels = ds2.ngff.channels
    assert channels is not None
    assert [c.label for c in channels] == ["DAPI", "GFP"]


def test_unknown_field_preserved(tmp_ome_zarr: Path, tmp_path: Path) -> None:
    """An arbitrary unknown carrier key survives write (rule 7, forward-compat)."""
    ds = open_ngff_dataset(str(tmp_ome_zarr))
    ds.attrs["ome"]["_experiment"] = {"id": 42}

    out = str(tmp_path / "unknown_field.ome.zarr")
    write_ngff_dataset(ds, out)

    ds2 = open_ngff_dataset(out)
    assert ds2.attrs["ome"].get("_experiment") == {"id": 42}


def test_edit_reflected_managed_field_wins(tmp_ome_zarr: Path, tmp_path: Path) -> None:
    """A set_scale edit is reflected on write: the managed multiscales subtree wins."""
    ds = open_ngff_dataset(str(tmp_ome_zarr))
    # Also carry an unknown key so we prove the merge keeps carrier-only data too.
    ds.attrs["ome"]["_experiment"] = {"id": 7}
    ds_edited = ds.ngff.set_scale(x=3.0)

    out = str(tmp_path / "edit_reflected.ome.zarr")
    write_ngff_dataset(ds_edited, out)

    ds2 = open_ngff_dataset(out)
    # New x scale (spacing between adjacent world coords) is present.
    np.testing.assert_allclose(float(ds2["x"].values[1] - ds2["x"].values[0]), 3.0, rtol=1e-6)
    # Carrier-only key still survived alongside the managed edit.
    assert ds2.attrs["ome"].get("_experiment") == {"id": 7}


def test_no_carrier_still_writes(tmp_path: Path) -> None:
    """A freshly-built Dataset with no ``attrs['ome']`` writes without error."""
    data = np.arange(100, dtype=np.float32).reshape(10, 10)
    ds = xr.Dataset(
        {"image": (["y", "x"], data)},
        coords={"y": np.arange(10) * 0.5, "x": np.arange(10) * 0.5},
    )
    assert "ome" not in ds.attrs

    out = str(tmp_path / "no_carrier.ome.zarr")
    write_ngff_dataset(ds, out)  # must not raise

    ds2 = open_ngff_dataset(out)
    np.testing.assert_array_equal(ds2["image"].compute().values, data)


def test_deep_merge_precedence() -> None:
    """deep_merge: nested dicts merge; override scalars win; base-only keys kept."""
    base = {"a": 1, "nested": {"x": 1, "y": 2}, "only_base": 9}
    override = {"a": 2, "nested": {"y": 3, "z": 4}, "only_over": 5}
    result = deep_merge(base, override)
    assert result == {
        "a": 2,
        "nested": {"x": 1, "y": 3, "z": 4},
        "only_base": 9,
        "only_over": 5,
    }
    # Inputs untouched.
    assert base["nested"] == {"x": 1, "y": 2}
