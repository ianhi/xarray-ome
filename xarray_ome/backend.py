"""Xarray backend for OME-Zarr files."""

from __future__ import annotations

import os
from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

from xarray.backends import BackendEntrypoint

from xarray_ome.reader import open_ome_dataset, open_ome_datatree

if TYPE_CHECKING:
    from xarray.core.dataset import Dataset
    from xarray.core.datatree import DataTree


class OmeZarrBackendEntrypoint(BackendEntrypoint):
    """Xarray backend for reading OME-Zarr files.

    This backend enables opening OME-Zarr files using xarray's native
    open_dataset() and open_datatree() functions with engine="ome-zarr".

    Examples
    --------
    >>> import xarray as xr
    >>> ds = xr.open_dataset("image.ome.zarr", engine="ome-zarr")
    >>> dt = xr.open_datatree("image.ome.zarr", engine="ome-zarr")
    """

    description = "Open OME-Zarr (OME-NGFF) files in xarray"
    url = "https://github.com/your-org/xarray-ome"
    supports_groups = True

    open_dataset_parameters = ("resolution", "validate")

    def open_dataset(  # type: ignore[override]
        self,
        filename_or_obj: str | os.PathLike[Any],
        *,
        drop_variables: str | Iterable[str] | None = None,
        resolution: int = 0,
        validate: bool = False,
    ) -> Dataset:
        """Open a single resolution level from an OME-Zarr store.

        Parameters
        ----------
        filename_or_obj : str or PathLike
            Path to the OME-Zarr store (local or remote URL).
        drop_variables : str or iterable of str, optional
            Variables to drop from the dataset.
        resolution : int, default 0
            Which resolution level to open (0 is highest resolution).
        validate : bool, default False
            Whether to validate metadata against OME-NGFF specification.

        Returns
        -------
        Dataset
            Dataset containing the requested resolution level.
        """
        path = str(filename_or_obj) if isinstance(filename_or_obj, os.PathLike) else filename_or_obj
        ds = open_ome_dataset(path, resolution=resolution, validate=validate)

        if drop_variables is not None:
            ds = ds.drop_vars(drop_variables)

        return ds

    def open_datatree(  # type: ignore[override]
        self,
        filename_or_obj: str | os.PathLike[Any],
        *,
        drop_variables: str | Iterable[str] | None = None,
        validate: bool = False,
    ) -> DataTree:
        """Open an OME-Zarr store as a DataTree with all resolution levels.

        Parameters
        ----------
        filename_or_obj : str or PathLike
            Path to the OME-Zarr store (local or remote URL).
        drop_variables : str or iterable of str, optional
            Variables to drop from all datasets in the tree.
        validate : bool, default False
            Whether to validate metadata against OME-NGFF specification.

        Returns
        -------
        DataTree
            DataTree containing all resolution levels.
        """
        path = str(filename_or_obj) if isinstance(filename_or_obj, os.PathLike) else filename_or_obj
        dt = open_ome_datatree(path, validate=validate)

        if drop_variables is not None:
            if isinstance(drop_variables, str):
                drop_variables = [drop_variables]

            for node in dt.subtree:
                if node.ds is not None:
                    vars_to_drop = [v for v in drop_variables if v in node.ds.data_vars]
                    if vars_to_drop:
                        node.ds = node.ds.drop_vars(vars_to_drop)

        return dt

    def guess_can_open(self, filename_or_obj: str | os.PathLike[Any] | Any) -> bool:
        """Guess whether this backend can open the given file.

        Parameters
        ----------
        filename_or_obj : str or PathLike
            File to check.

        Returns
        -------
        bool
            True if the file appears to be an OME-Zarr store.
        """
        if isinstance(filename_or_obj, str | os.PathLike):
            path_str = str(filename_or_obj).rstrip("/")
            _, ext = os.path.splitext(path_str)
            return ext in [".zarr"]

        return False
