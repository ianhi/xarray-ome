"""Pytest fixtures for xarray-ome tests."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import pytest
from ngff_zarr import to_multiscales, to_ngff_image, to_ngff_zarr  # type: ignore[import-untyped]

if TYPE_CHECKING:
    from collections.abc import Generator


@pytest.fixture
def tmp_ome_zarr(tmp_path: Path) -> Generator[Path, None, None]:
    """Create a temporary OME-Zarr file for testing."""
    # Create small test data (2 channels, 5 z-slices, 10x10 pixels)
    data = np.random.randint(0, 255, size=(2, 5, 10, 10), dtype=np.uint8)
    dims = ["c", "z", "y", "x"]
    scale = {"c": 1.0, "z": 0.5, "y": 0.25, "x": 0.25}
    translation = {"c": 0.0, "z": 0.0, "y": 0.0, "x": 0.0}
    axes_units = {"c": None, "z": "micrometer", "y": "micrometer", "x": "micrometer"}

    # Create NgffImage
    ngff_image = to_ngff_image(
        data,
        dims=dims,
        scale=scale,
        translation=translation,
        name="test_image",
        axes_units=axes_units,
    )

    # Create multiscales with 2 additional downsampled levels
    multiscales = to_multiscales(ngff_image, scale_factors=[2, 4])

    # Write to temporary path
    output_path = tmp_path / "test.ome.zarr"
    to_ngff_zarr(str(output_path), multiscales)

    yield output_path


@pytest.fixture
def tmp_ome_zarr_single_scale(tmp_path: Path) -> Generator[Path, None, None]:
    """Create a temporary single-scale OME-Zarr file for testing."""
    # Create small test data (single z-slice, 8x8 pixels)
    data = np.arange(64, dtype=np.float32).reshape(8, 8)
    dims = ["y", "x"]
    scale = {"y": 1.0, "x": 1.0}
    translation = {"y": 0.0, "x": 0.0}

    # Create NgffImage
    ngff_image = to_ngff_image(
        data,
        dims=dims,
        scale=scale,
        translation=translation,
        name="simple_image",
    )

    # Create multiscales with no downsampling
    multiscales = to_multiscales(ngff_image, scale_factors=[])

    # Write to temporary path
    output_path = tmp_path / "single_scale.ome.zarr"
    to_ngff_zarr(str(output_path), multiscales)

    yield output_path


@pytest.fixture
def sample_data_3d() -> np.ndarray:
    """Create sample 3D data for testing."""
    return np.random.randint(0, 100, size=(5, 10, 10), dtype=np.uint16)


@pytest.fixture
def sample_dims_3d() -> list[str]:
    """Sample dimension names for 3D data."""
    return ["z", "y", "x"]


@pytest.fixture
def sample_scale_3d() -> dict[str, float]:
    """Sample scale factors for 3D data."""
    return {"z": 0.5, "y": 0.25, "x": 0.25}


@pytest.fixture
def sample_translation_3d() -> dict[str, float]:
    """Sample translation offsets for 3D data."""
    return {"z": 0.0, "y": 0.0, "x": 0.0}
