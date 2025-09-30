"""Utilities for detecting and working with OME-Zarr stores."""

from __future__ import annotations


def _detect_store_type(path: str) -> str:
    """
    Detect the type of OME-Zarr store.

    Parameters
    ----------
    path : str
        Path or URL to the OME-Zarr store

    Returns
    -------
    str
        Store type: 'image', 'hcs', or 'unknown'
    """
    try:
        from ngff_zarr import from_hcs_zarr

        try:
            from_hcs_zarr(path)
            return "hcs"
        except Exception:
            pass

        from ngff_zarr import from_ngff_zarr

        try:
            from_ngff_zarr(path)
            return "image"
        except Exception:
            pass

        return "unknown"
    except Exception:
        return "unknown"
