"""Utilities for detecting and working with OME-Zarr stores."""

from __future__ import annotations

from typing import Any


def _detect_store_type(path: str) -> str:
    """
    Detect the type of OME-Zarr store by inspecting metadata.

    Parameters
    ----------
    path : str
        Path or URL to the OME-Zarr store

    Returns
    -------
    str
        Store type: 'image', 'hcs', or 'unknown'

    Notes
    -----
    Uses ngff-zarr's validate function to attempt validation against
    different OME-NGFF models (image, plate, well).
    """
    try:
        import zarr
        from ngff_zarr import validate  # type: ignore[import-untyped]

        store = zarr.open(path, mode="r")
        attrs: dict[str, Any] = dict(store.attrs.asdict())

        try:
            validate(attrs, model="image")
            return "image"
        except Exception:
            pass

        try:
            validate(attrs, model="plate")
            return "hcs"
        except Exception:
            pass

        try:
            validate(attrs, model="well")
            return "hcs"
        except Exception:
            pass

        return "unknown"
    except Exception:
        return "unknown"
