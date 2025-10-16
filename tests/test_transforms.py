"""Tests for coordinate transformation utilities."""

from __future__ import annotations

from typing import Hashable

import numpy as np
import xarray as xr

from xarray_ome.transforms import coords_to_transforms, transforms_to_coords


def test_transforms_to_coords_basic() -> None:
    """Test basic coordinate transformation."""
    shape = (5, 10, 10)
    dims = ["z", "y", "x"]
    scale = {"z": 0.5, "y": 0.25, "x": 0.25}
    translation = {"z": 0.0, "y": 0.0, "x": 0.0}

    coords = transforms_to_coords(shape, dims, scale, translation)

    # Check z coordinates
    assert len(coords["z"]) == 5
    np.testing.assert_allclose(coords["z"], [0.0, 0.5, 1.0, 1.5, 2.0])

    # Check y coordinates
    assert len(coords["y"]) == 10
    np.testing.assert_allclose(coords["y"][:3], [0.0, 0.25, 0.5])

    # Check x coordinates
    assert len(coords["x"]) == 10
    np.testing.assert_allclose(coords["x"][:3], [0.0, 0.25, 0.5])


def test_transforms_to_coords_with_translation() -> None:
    """Test coordinate transformation with translation."""
    shape = (3,)
    dims = ["x"]
    scale = {"x": 2.0}
    translation = {"x": 10.0}

    coords = transforms_to_coords(shape, dims, scale, translation)

    # x = translation + scale * indices
    # x = 10.0 + 2.0 * [0, 1, 2] = [10.0, 12.0, 14.0]
    np.testing.assert_allclose(coords["x"], [10.0, 12.0, 14.0])


def test_transforms_to_coords_missing_dimension() -> None:
    """Test that missing dimensions default to scale=1.0, translation=0.0."""
    shape = (5,)
    dims = ["z"]
    scale: dict[str, float] = {}  # Empty - should default
    translation: dict[str, float] = {}  # Empty - should default

    coords = transforms_to_coords(shape, dims, scale, translation)

    # Should default to scale=1.0, translation=0.0
    np.testing.assert_allclose(coords["z"], [0.0, 1.0, 2.0, 3.0, 4.0])


def test_coords_to_transforms_from_dataset(
    sample_data_3d: np.ndarray,
    sample_dims_3d: list[str],
    sample_scale_3d: dict[str, float],
    sample_translation_3d: dict[str, float],
) -> None:
    """Test extracting transforms from a Dataset with coordinates."""
    # Create coordinates
    coords = transforms_to_coords(
        sample_data_3d.shape,
        sample_dims_3d,
        sample_scale_3d,
        sample_translation_3d,
    )

    # Create Dataset
    ds = xr.Dataset(
        {"image": (sample_dims_3d, sample_data_3d)},
        coords=coords,
    )

    # Store metadata (simulating what we do in reader)
    ds.attrs["ome_scale"] = sample_scale_3d
    ds.attrs["ome_translation"] = sample_translation_3d

    # Extract transforms
    scale: dict[Hashable, float]
    translation: dict[Hashable, float]
    scale, translation = coords_to_transforms(ds)

    # Should retrieve from attrs (convert to dict for comparison)
    assert dict(scale) == sample_scale_3d
    assert dict(translation) == sample_translation_3d


def test_coords_to_transforms_computed_from_coords() -> None:
    """Test computing transforms from coordinate arrays when attrs not present."""
    # Create Dataset with coordinates but no attrs
    data = np.arange(12).reshape(3, 4)
    ds = xr.Dataset(
        {"image": (["y", "x"], data)},
        coords={
            "y": np.array([0.0, 0.5, 1.0]),
            "x": np.array([0.0, 0.25, 0.5, 0.75]),
        },
    )

    # Extract transforms (should compute from coordinates)
    scale: dict[Hashable, float]
    translation: dict[Hashable, float]
    scale, translation = coords_to_transforms(ds)

    # Check scale (spacing between coordinates)
    assert scale["y"] == 0.5
    assert scale["x"] == 0.25

    # Check translation (first coordinate value)
    assert translation["y"] == 0.0
    assert translation["x"] == 0.0


def test_coords_to_transforms_with_translation() -> None:
    """Test computing transforms with non-zero translation."""
    data = np.arange(9).reshape(3, 3)
    ds = xr.Dataset(
        {"image": (["y", "x"], data)},
        coords={
            "y": np.array([10.0, 11.0, 12.0]),
            "x": np.array([5.0, 5.5, 6.0]),
        },
    )

    scale: dict[Hashable, float]
    translation: dict[Hashable, float]
    scale, translation = coords_to_transforms(ds)

    assert scale["y"] == 1.0
    assert scale["x"] == 0.5
    assert translation["y"] == 10.0
    assert translation["x"] == 5.0


def test_roundtrip_transforms() -> None:
    """Test that transforms -> coords -> transforms is lossless."""
    shape = (2, 5, 10, 10)
    dims = ["c", "z", "y", "x"]
    scale_original = {"c": 1.0, "z": 0.5, "y": 0.25, "x": 0.25}
    translation_original = {"c": 0.0, "z": 1.0, "y": 2.0, "x": 3.0}

    # Convert to coordinates
    coords = transforms_to_coords(shape, dims, scale_original, translation_original)

    # Create Dataset
    ds = xr.Dataset(
        {"image": (dims, np.zeros(shape))},
        coords=coords,
    )
    ds.attrs["ome_scale"] = scale_original
    ds.attrs["ome_translation"] = translation_original

    # Convert back to transforms
    scale_roundtrip, translation_roundtrip = coords_to_transforms(ds)

    # Should match original
    assert scale_roundtrip == scale_original
    assert translation_roundtrip == translation_original


def test_transforms_to_coords_2d() -> None:
    """Test with 2D data (no z dimension)."""
    shape = (100, 100)
    dims = ["y", "x"]
    scale = {"y": 0.1, "x": 0.1}
    translation = {"y": 0.0, "x": 0.0}

    coords = transforms_to_coords(shape, dims, scale, translation)

    assert len(coords) == 2
    assert "y" in coords
    assert "x" in coords
    assert len(coords["y"]) == 100
    assert len(coords["x"]) == 100


def test_transforms_to_coords_5d() -> None:
    """Test with 5D data (t, c, z, y, x)."""
    shape = (3, 2, 5, 10, 10)
    dims = ["t", "c", "z", "y", "x"]
    scale = {"t": 1.0, "c": 1.0, "z": 0.5, "y": 0.25, "x": 0.25}
    translation = {"t": 0.0, "c": 0.0, "z": 0.0, "y": 0.0, "x": 0.0}

    coords = transforms_to_coords(shape, dims, scale, translation)

    assert len(coords) == 5
    for dim in dims:
        assert dim in coords
