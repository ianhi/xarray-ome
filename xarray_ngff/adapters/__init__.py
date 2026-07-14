"""Adapters that bring images loaded by other libraries into the xarray-ngff layer.

Each adapter takes an object produced by a third-party reader and returns *our*
representation: real axis dims, lazy physical coordinates with units, omero
channel labels, and the verbatim ``ome`` carrier surfaced through ``.ngff``.

Currently:

- :func:`xarray_ngff.adapters.bioio.from_bioio` -- rebuild our representation
  from a :class:`bioio.BioImage` (or its ``xarray_dask_data``).
"""

from __future__ import annotations

from .bioio import from_bioio, from_bioio_datatree

__all__ = ["from_bioio", "from_bioio_datatree"]
