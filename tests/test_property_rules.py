"""Property tests for the four core NGFF<->xarray rules, driven by the
``ome-zarr-hypothesis`` generator.

The generator (a sibling package, ``../ome-zarr-hypothesis``) produces a broad,
*schema-valid* stream of OME-Zarr documents. Here we feed the slice of that
stream that ``xarray_ngff`` can actually read -- i.e. the **ngff-zarr
representable subset** (canonical ``t/c/z/y/x`` axes, ``space/time/channel``
types; every omero channel carries a ``color`` so ngff-zarr's reader does not
crash, see ozh finding F21) -- through the package's public API and assert the
package's own design invariants hold *across the generated space* rather than on
a handful of hand-built fixtures:

- **Rule 2/3 -- ``.sel`` always works.** Scalar and inclusive-slice selection on
  every physical coordinate succeeds regardless of calibration.
- **Rule 4 -- never fabricate units.** An axis is ``.ngff.calibrated`` iff the
  store declared a unit for it; a unit is surfaced only when declared.
- **Rule 7 -- never lose data.** An unknown carrier field and the verbatim
  ``omero`` block survive a write round-trip (Dataset and DataTree).
- **Rule 8 -- round-trip is testable.** ``open -> write -> open`` reproduces the
  axis names and (finest-level) physical coordinates.

The generator requires Python >=3.12; on an older interpreter this whole module
is skipped (the package itself stays 3.11+).
"""

from __future__ import annotations

import tempfile
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

import numpy as np
import pytest

pytest.importorskip("hypothesis")
pytest.importorskip("ome_zarr_hypothesis")

import zarr  # noqa: E402
from hypothesis import HealthCheck, assume, given, settings  # noqa: E402
from ome_zarr_hypothesis import (  # noqa: E402
    is_representable_subset,
    materializable_image,
    write_ome_zarr,
)
from ome_zarr_hypothesis.axes import axes as axes_strategy  # noqa: E402

from xarray_ngff import (  # noqa: E402
    open_ngff_dataset,
    open_ngff_datatree,
    write_ngff_dataset,
    write_ngff_datatree,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

    from hypothesis.strategies import SearchStrategy

# Physical axes the reader gives a lazy affine coordinate (mirrors
# reader._PHYSICAL_AXES); ``c`` carries labels/positions, never an affine coord.
_PHYSICAL = ("t", "z", "y", "x")

# Disk I/O per example -> no deadline. ``max_examples`` is inherited from the
# active Hypothesis profile (see tests/conftest.py: dev/default/ci), selectable
# with HYPOTHESIS_PROFILE, so coverage scales without editing this module.
_SETTINGS = settings(
    deadline=None,
    suppress_health_check=[
        HealthCheck.too_slow,
        HealthCheck.data_too_large,
        HealthCheck.filter_too_much,
    ],
)


def _canonical_names(axlist: list[dict[str, Any]]) -> bool:
    """True when every axis uses its canonical single-letter name for its role.

    Keeps role<->name unambiguous (time->t, channel->c, space->z/y/x) so the
    reader's name-keyed coordinate logic is exercised on well-formed input.
    ``ome_zarr_hypothesis.axes`` biases toward this assignment, so filtering the
    (cheap) axes sub-strategy rejects little.
    """
    for a in axlist:
        t, n = a.get("type"), a.get("name")
        if t == "time" and n != "t":
            return False
        if t == "channel" and n != "c":
            return False
        if t == "space" and n not in ("z", "y", "x"):
            return False
    return True


# Canonical, ngff-zarr-representable axes (no typeless/custom axes).
_CANONICAL_AXES = axes_strategy(allow_custom=False).filter(_canonical_names)


def _normalize(doc: dict[str, Any]) -> dict[str, Any]:
    """Make a generated doc readable+writable without touching what we test.

    Two incidental generation artifacts would otherwise crash the *substrate*
    (ngff-zarr) rather than exercise an ``xarray_ngff`` rule, so we neutralize
    them here:

    * a ``multiscales[].name`` of arbitrary unicode: the reader turns it into
      the data-variable name, which ngff-zarr's *writer* then uses as a Zarr
      node path -- exotic characters raise ``OSError`` on write. The name is not
      one of the four rules, so we drop it (the reader falls back to ``image``).
    * an omero channel with no ``color``: ngff-zarr's reader crashes with
      ``KeyError: 'color'`` (ozh finding F21) even though ``color`` is
      schema-optional. We default it; the block still round-trips verbatim.
    """
    for ms in doc["ome"].get("multiscales", []):
        ms.pop("name", None)
    omero = doc["ome"].get("omero")
    if isinstance(omero, dict):
        for ch in omero.get("channels", []):
            ch.setdefault("color", "FFFFFF")
    return doc


def readable_pairs(
    *, with_omero: bool, label: bool = False
) -> SearchStrategy[tuple[dict[str, Any], dict[str, Any]]]:
    """``(metadata, arrays)`` pairs ``xarray_ngff`` can read, version 0.5.

    Constrained to canonical axes; ``is_representable_subset`` is applied as a
    belt-and-braces gate. With ``with_omero=True`` an omero block is always
    attached (channel-axis mismatch allowed -- the block still round-trips).
    With ``label=True`` a *label* document is drawn (integer dtype + an
    ``image-label`` block) instead of a plain image. Incidental substrate
    hazards are neutralized by :func:`_normalize`.
    """
    # omero kwargs apply only to image docs; label_metadata does not accept them.
    omero_kwargs: dict[str, Any] = (
        {} if label else {"with_omero": with_omero, "allow_omero_channel_mismatch": with_omero}
    )
    return (
        materializable_image(
            version="0.5",
            axes=_CANONICAL_AXES,
            label=label,
            **omero_kwargs,
        )
        .map(lambda p: (_normalize(p[0]), p[1]))
        .filter(lambda p: is_representable_subset(p[0]))
    )


# Non-representable docs: axes that violate the canonical role<->name mapping
# (e.g. a ``space`` axis named ``t`` -- the negation of :func:`_canonical_names`),
# which the reader must reject cleanly rather than crash on. ``allow_custom`` stays
# on so custom/typeless axes -- also outside the representable subset -- are in the mix.
_NON_REPRESENTABLE_PAIRS = (
    materializable_image(
        version="0.5", axes=axes_strategy().filter(lambda ax: not _canonical_names(ax))
    )
    .map(lambda p: (_normalize(p[0]), p[1]))
    .filter(lambda p: not is_representable_subset(p[0]))
)


@contextmanager
def _written_store(pair: tuple[dict[str, Any], dict[str, Any]]) -> Iterator[str]:
    """Materialize a ``(metadata, arrays)`` pair to a fresh temp OME-Zarr store."""
    metadata, arrays = pair
    with tempfile.TemporaryDirectory() as d:
        write_ome_zarr(zarr.storage.LocalStore(d), metadata, arrays)
        yield d


# ---------------------------------------------------------------------------
# Rule 2/3: .sel always works (pixels or world), for scalar and inclusive slice
# ---------------------------------------------------------------------------
@_SETTINGS
@given(pair=readable_pairs(with_omero=False))
def test_sel_always_works(pair: tuple[dict[str, Any], dict[str, Any]]) -> None:
    with _written_store(pair) as store:
        ds = open_ngff_dataset(store)
        var = next(iter(ds.data_vars))
        for axis in _PHYSICAL:
            if axis not in ds.coords:
                continue
            values = np.asarray(ds[axis].values)
            mid = float(values[len(values) // 2])

            # Scalar selection: a labelled point must resolve without error.
            scalar = ds.sel({axis: mid})
            assert var in scalar.data_vars

            # Inclusive slice over the full label span returns the whole axis.
            lo, hi = float(values.min()), float(values.max())
            sliced = ds.sel({axis: slice(lo, hi)})
            assert 1 <= sliced.sizes[axis] <= ds.sizes[axis]


# ---------------------------------------------------------------------------
# Rule 4: never fabricate units -- calibrated iff a unit was declared
# ---------------------------------------------------------------------------
@_SETTINGS
@given(pair=readable_pairs(with_omero=False))
def test_never_fabricate_units(pair: tuple[dict[str, Any], dict[str, Any]]) -> None:
    with _written_store(pair) as store:
        ds = open_ngff_dataset(store)
        calibrated = ds.ngff.calibrated
        units = ds.ngff.units
        for axis in ds.ngff.axes:
            declared = axis.unit is not None
            # Calibration state must exactly reflect whether a unit was declared.
            assert calibrated[axis.name] is declared
            if declared:
                assert units[axis.name] == axis.unit
            else:
                # No coord ``units`` attr may be invented for an uncalibrated axis.
                coord = ds.coords.get(axis.name)
                if coord is not None:
                    assert "units" not in coord.attrs


# ---------------------------------------------------------------------------
# Rule 7: never lose data -- unknown carrier field survives a write
# ---------------------------------------------------------------------------
@_SETTINGS
@given(pair=readable_pairs(with_omero=False))
def test_unknown_carrier_field_preserved(pair: tuple[dict[str, Any], dict[str, Any]]) -> None:
    with _written_store(pair) as store:
        ds = open_ngff_dataset(store)
        ds.attrs["ome"]["_probe"] = {"unmodelled": [1, 2, 3]}
        with tempfile.TemporaryDirectory() as out:
            write_ngff_dataset(ds, out)
            ds2 = open_ngff_dataset(out)
        assert ds2.ngff.raw.get("_probe") == {"unmodelled": [1, 2, 3]}


# ---------------------------------------------------------------------------
# Rule 8: round-trip reproduces axis names and finest-level physical coords
# ---------------------------------------------------------------------------
@_SETTINGS
@given(pair=readable_pairs(with_omero=False))
def test_roundtrip_dataset_fidelity(pair: tuple[dict[str, Any], dict[str, Any]]) -> None:
    with _written_store(pair) as store:
        ds = open_ngff_dataset(store)
        with tempfile.TemporaryDirectory() as out:
            write_ngff_dataset(ds, out)
            ds2 = open_ngff_dataset(out)

        assert [a.name for a in ds2.ngff.axes] == [a.name for a in ds.ngff.axes]
        for axis in _PHYSICAL:
            if axis in ds.coords:
                np.testing.assert_allclose(
                    np.asarray(ds2[axis].values),
                    np.asarray(ds[axis].values),
                    rtol=1e-6,
                    atol=1e-9,
                )


# ---------------------------------------------------------------------------
# Rule 7 (+8): the verbatim omero block survives a write, Dataset & DataTree
# ---------------------------------------------------------------------------
@_SETTINGS
@given(pair=readable_pairs(with_omero=True))
def test_omero_carrier_roundtrip_dataset(pair: tuple[dict[str, Any], dict[str, Any]]) -> None:
    with _written_store(pair) as store:
        ds = open_ngff_dataset(store)
        original = ds.ngff.raw.get("omero")
        assert original is not None  # with_omero=True always attaches it
        with tempfile.TemporaryDirectory() as out:
            write_ngff_dataset(ds, out)
            ds2 = open_ngff_dataset(out)
        assert ds2.ngff.raw.get("omero") == original
        channels = ds2.ngff.channels
        assert channels is not None
        assert len(channels) == len(original["channels"])


@_SETTINGS
@given(pair=readable_pairs(with_omero=True))
def test_omero_carrier_roundtrip_datatree(pair: tuple[dict[str, Any], dict[str, Any]]) -> None:
    with _written_store(pair) as store:
        dt = open_ngff_datatree(store)
        original = dt.ngff.raw.get("omero")
        assert original is not None
        dt.attrs["ome"]["_probe"] = {"kept": True}
        with tempfile.TemporaryDirectory() as out:
            write_ngff_datatree(dt, out)
            dt2 = open_ngff_datatree(out)
        # Unknown field (rule 7) and the verbatim omero block both survive.
        assert dt2.ngff.raw.get("_probe") == {"kept": True}
        assert dt2.ngff.raw.get("omero") == original
        # Finest-level axis names are preserved (rule 8).
        assert [a.name for a in dt2.ngff.axes] == [a.name for a in dt.ngff.axes]


# ---------------------------------------------------------------------------
# Rule 2 on size-1 axes (single z-slice / single timepoint). This regressed on
# xarray <=2025.9.1 (a lazy CoordinateTransform-backed dim reduced to length 1
# built a 0-d coordinate and raised); fixed in xarray 2026.1.0, which is our
# floor. See notes/upstream-ideas.md.
# ---------------------------------------------------------------------------
def test_sel_size1_axis(tmp_path: Any) -> None:
    """A size-1 physical axis must still support ``.sel`` (Rule 2)."""
    metadata = {
        "ome": {
            "version": "0.5",
            "multiscales": [
                {
                    "axes": [
                        {"name": "y", "type": "space"},
                        {"name": "x", "type": "space"},
                    ],
                    "datasets": [
                        {
                            "path": "0",
                            "coordinateTransformations": [{"type": "scale", "scale": [1.0, 1.0]}],
                        }
                    ],
                }
            ],
        }
    }
    arrays = {"0": np.zeros((1, 4), dtype=np.uint8)}  # y is size 1
    store = str(tmp_path / "size1.ome.zarr")
    write_ome_zarr(zarr.storage.LocalStore(store), metadata, arrays)
    ds = open_ngff_dataset(store)
    # Inclusive slice over the (single) label span -> should keep the 1 pixel.
    yval = float(np.asarray(ds["y"].values)[0])
    selected = ds.sel(y=slice(yval, yval))
    assert selected.sizes["y"] == 1


# ---------------------------------------------------------------------------
# Rule 8 on a multiscale DataTree: EVERY level's physical scale round-trips, not
# just the finest. The datatree writer used to copy level-0's coordinate
# transformations onto every coarser level (write_ngff_datatree deep-copied
# ``datasets[0]`` and only rewrote the path), so a coarse level's scale silently
# reverted to the finest level's on write. This pins that a pyramid with
# DISTINCT per-level scales survives open -> write -> open at every level.
# ---------------------------------------------------------------------------
def test_datatree_coarse_level_scale_roundtrip(tmp_path: Any) -> None:
    """Each pyramid level's scale must round-trip through the DataTree writer."""
    # Two levels with deliberately non-power-of-two, distinct scales so a
    # level-0 copy would be detected: level 0 scale 2.0, level 1 scale 7.0.
    level_scales = {"0": 2.0, "1": 7.0}
    metadata = {
        "ome": {
            "version": "0.5",
            "multiscales": [
                {
                    "axes": [
                        {"name": "y", "type": "space"},
                        {"name": "x", "type": "space"},
                    ],
                    "datasets": [
                        {
                            "path": path,
                            "coordinateTransformations": [{"type": "scale", "scale": [s, s]}],
                        }
                        for path, s in level_scales.items()
                    ],
                }
            ],
        }
    }
    arrays = {
        "0": np.zeros((8, 8), dtype=np.uint8),
        "1": np.zeros((4, 4), dtype=np.uint8),
    }
    store = str(tmp_path / "pyramid.ome.zarr")
    write_ome_zarr(zarr.storage.LocalStore(store), metadata, arrays)

    dt = open_ngff_datatree(store)
    # Capture each level's finest coordinate value (scale * index) before writing.
    original = {level: np.asarray(dt[level].ds["y"].values) for level in level_scales}

    out = str(tmp_path / "out.ome.zarr")
    write_ngff_datatree(dt, out)
    dt2 = open_ngff_datatree(out)

    for level in level_scales:
        np.testing.assert_allclose(
            np.asarray(dt2[level].ds["y"].values),
            original[level],
            rtol=1e-6,
            atol=1e-9,
            err_msg=f"level {level!r} scale did not round-trip",
        )


# ---------------------------------------------------------------------------
# Rule 7 on LABEL documents: the reader carries the (unmodelled) ``image-label``
# block verbatim, and it survives a write round-trip -- broadening the generator
# surface from plain images to label docs.
# ---------------------------------------------------------------------------
@_SETTINGS
@given(pair=readable_pairs(with_omero=False, label=True))
def test_image_label_carrier_roundtrip(pair: tuple[dict[str, Any], dict[str, Any]]) -> None:
    with _written_store(pair) as store:
        ds = open_ngff_dataset(store)
        original = ds.ngff.raw.get("image-label")
        assert original is not None  # label=True always attaches an image-label block
        with tempfile.TemporaryDirectory() as out:
            write_ngff_dataset(ds, out)
            ds2 = open_ngff_dataset(out)
        # The verbatim label block is preserved (rule 7), unchanged.
        assert ds2.ngff.raw.get("image-label") == original


# ---------------------------------------------------------------------------
# Robustness: a document OUTSIDE the ngff-zarr representable subset (here, axes
# that break the canonical role<->name mapping) must be REJECTED cleanly -- the
# reader raises a plain ``ValueError``, never crashing with a lower-level
# exception (KeyError/TypeError/AttributeError). Reading may also legitimately
# succeed when the reader is more permissive than the strict subset gate; only an
# *uncontrolled* failure is a bug.
# ---------------------------------------------------------------------------
@_SETTINGS
@given(pair=_NON_REPRESENTABLE_PAIRS)
def test_non_representable_reader_errors_cleanly(
    pair: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    metadata, arrays = pair
    with tempfile.TemporaryDirectory() as d:
        try:
            write_ome_zarr(zarr.storage.LocalStore(d), metadata, arrays)
        except Exception:  # noqa: BLE001
            # A substrate (ngff-zarr writer) limitation, not the reader's job.
            assume(False)
        # Either a clean read or a clean, typed ValueError -- nothing else.
        try:
            open_ngff_dataset(d)
        except ValueError:
            pass


# ---------------------------------------------------------------------------
# Version 0.6.dev4 is generated by ome-zarr-hypothesis but NOT yet readable here:
# ngff-zarr rejects ``0.6.dev`` version strings (see package handoff item 4). This
# is a deliberate, documented gap -- skipped, not silently omitted, so it surfaces
# the day ngff-zarr gains 0.6 read support.
# ---------------------------------------------------------------------------
@pytest.mark.skip(reason="ngff-zarr rejects 0.6.dev version strings; no 0.6 read path yet")
def test_version_06_readable() -> None:  # pragma: no cover - intentional placeholder
    raise AssertionError("unreachable: revisit when ngff-zarr reads 0.6")
