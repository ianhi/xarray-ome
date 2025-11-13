"""Tests for bidirectional OME-NGFF metadata <-> xarray conversion."""

import numpy as np
import xarray as xr

from xarray_ome.metadata import metadata_to_xarray_attrs, xarray_to_metadata


class TestMetadataToXarrayAttrs:
    """Test conversion from OME-NGFF metadata to xarray attrs."""

    def test_basic_metadata(self) -> None:
        """Test extraction of basic name and version."""
        metadata = {
            "name": "test_image",
            "version": "0.4",
        }

        attrs = metadata_to_xarray_attrs(metadata)

        assert attrs["ome_name"] == "test_image"
        assert attrs["ome_version"] == "0.4"
        assert attrs["ome_ngff_metadata"] == metadata

    def test_axes_types(self) -> None:
        """Test extraction of axis types."""
        metadata = {
            "axes": [
                {"name": "c", "type": "channel"},
                {"name": "z", "type": "space"},
                {"name": "y", "type": "space"},
                {"name": "x", "type": "space"},
            ],
        }

        attrs = metadata_to_xarray_attrs(metadata)

        assert attrs["ome_axes_types"] == ["channel", "space", "space", "space"]

    def test_axes_units(self) -> None:
        """Test extraction of axis units."""
        metadata = {
            "axes": [
                {"name": "c", "type": "channel"},
                {"name": "z", "type": "space", "unit": "micrometer"},
                {"name": "y", "type": "space", "unit": "micrometer"},
                {"name": "x", "type": "space", "unit": "micrometer"},
            ],
        }

        attrs = metadata_to_xarray_attrs(metadata)

        assert attrs["ome_axes_units"] == {
            "z": "micrometer",
            "y": "micrometer",
            "x": "micrometer",
        }

    def test_axes_orientations(self) -> None:
        """Test extraction of axis orientations."""
        metadata = {
            "axes": [
                {"name": "z", "type": "space", "orientation": "anterior-posterior"},
                {"name": "y", "type": "space", "orientation": "left-right"},
                {"name": "x", "type": "space", "orientation": "superior-inferior"},
            ],
        }

        attrs = metadata_to_xarray_attrs(metadata)

        assert attrs["ome_axes_orientations"] == {
            "z": "anterior-posterior",
            "y": "left-right",
            "x": "superior-inferior",
        }

    def test_multiscale_info(self) -> None:
        """Test extraction of multiscale paths and count."""
        metadata = {
            "datasets": [
                {"path": "0"},
                {"path": "1"},
                {"path": "2"},
            ],
        }

        attrs = metadata_to_xarray_attrs(metadata)

        assert attrs["ome_multiscale_paths"] == ["0", "1", "2"]
        assert attrs["ome_num_resolutions"] == 3

    def test_channel_colors(self) -> None:
        """Test extraction of channel colors."""
        metadata = {
            "omero": {
                "channels": [
                    {"label": "DAPI", "color": "0000FF"},
                    {"label": "GFP", "color": "00FF00"},
                ],
            },
        }

        attrs = metadata_to_xarray_attrs(metadata)

        assert attrs["ome_channel_colors"] == ["0000FF", "00FF00"]

    def test_channel_windows(self) -> None:
        """Test extraction of channel rendering windows."""
        metadata = {
            "omero": {
                "channels": [
                    {
                        "label": "DAPI",
                        "window": {"min": 0.0, "max": 65535.0, "start": 0.0, "end": 1500.0},
                    },
                    {
                        "label": "GFP",
                        "window": {"min": 0.0, "max": 65535.0, "start": 0.0, "end": 2000.0},
                    },
                ],
            },
        }

        attrs = metadata_to_xarray_attrs(metadata)

        assert len(attrs["ome_channel_windows"]) == 2
        assert attrs["ome_channel_windows"][0]["end"] == 1500.0
        assert attrs["ome_channel_windows"][1]["end"] == 2000.0

    def test_full_metadata_preserved(self) -> None:
        """Test that full metadata dict is always preserved."""
        metadata = {
            "name": "test",
            "version": "0.4",
            "custom_field": "should_be_preserved",
            "nested": {"deep": {"field": 123}},
        }

        attrs = metadata_to_xarray_attrs(metadata)

        assert attrs["ome_ngff_metadata"] == metadata
        assert attrs["ome_ngff_metadata"]["custom_field"] == "should_be_preserved"
        assert attrs["ome_ngff_metadata"]["nested"]["deep"]["field"] == 123

    def test_channel_labels_not_in_attrs(self) -> None:
        """Test that channel labels are NOT extracted to attrs (they go in coords)."""
        metadata = {
            "omero": {
                "channels": [
                    {"label": "DAPI"},
                    {"label": "GFP"},
                ],
            },
        }

        attrs = metadata_to_xarray_attrs(metadata)

        # Channel labels should NOT be in attrs
        assert "ome_channels" not in attrs
        assert "ome_channel_labels" not in attrs


class TestXarrayToMetadata:
    """Test conversion from xarray Dataset back to OME-NGFF metadata."""

    def test_basic_reconstruction(self) -> None:
        """Test reconstruction of basic metadata."""
        ds = xr.Dataset(
            {"image": xr.DataArray(np.zeros((10, 10)), dims=["y", "x"])},
        )
        ds.attrs["ome_name"] = "test_image"
        ds.attrs["ome_version"] = "0.4"

        metadata = xarray_to_metadata(ds, preserve_original=False)

        assert metadata["name"] == "test_image"
        assert metadata["version"] == "0.4"

    def test_axes_reconstruction(self) -> None:
        """Test reconstruction of axes metadata."""
        ds = xr.Dataset(
            {"image": xr.DataArray(np.zeros((2, 10, 10)), dims=["c", "y", "x"])},
        )
        ds.attrs["ome_axes_types"] = ["channel", "space", "space"]
        ds.attrs["ome_axes_units"] = {"y": "micrometer", "x": "micrometer"}

        metadata = xarray_to_metadata(ds, preserve_original=False)

        assert len(metadata["axes"]) == 3
        assert metadata["axes"][0] == {"name": "c", "type": "channel"}
        assert metadata["axes"][1] == {"name": "y", "type": "space", "unit": "micrometer"}
        assert metadata["axes"][2] == {"name": "x", "type": "space", "unit": "micrometer"}

    def test_channel_labels_from_coords(self) -> None:
        """Test reconstruction of channel labels from coordinate values."""
        ds = xr.Dataset(
            {
                "image": xr.DataArray(
                    np.zeros((2, 10, 10)),
                    dims=["c", "y", "x"],
                    coords={"c": ["DAPI", "GFP"]},
                ),
            },
        )
        ds.attrs["ome_channel_colors"] = ["0000FF", "00FF00"]

        metadata = xarray_to_metadata(ds, preserve_original=False)

        assert "omero" in metadata
        assert "channels" in metadata["omero"]
        channels = metadata["omero"]["channels"]
        assert len(channels) == 2
        assert channels[0]["label"] == "DAPI"
        assert channels[0]["color"] == "0000FF"
        assert channels[1]["label"] == "GFP"
        assert channels[1]["color"] == "00FF00"

    def test_preserve_original_metadata(self) -> None:
        """Test that original metadata is preserved when requested."""
        original_metadata = {
            "name": "original",
            "version": "0.4",
            "custom_field": "preserved",
            "nested": {"data": 123},
        }

        ds = xr.Dataset(
            {"image": xr.DataArray(np.zeros((10, 10)), dims=["y", "x"])},
        )
        ds.attrs["ome_ngff_metadata"] = original_metadata
        ds.attrs["ome_name"] = "modified"  # This should override

        metadata = xarray_to_metadata(ds, preserve_original=True)

        # Updated field
        assert metadata["name"] == "modified"
        # Preserved custom fields
        assert metadata["custom_field"] == "preserved"
        assert metadata["nested"]["data"] == 123

    def test_channel_windows_reconstruction(self) -> None:
        """Test reconstruction of channel rendering windows."""
        ds = xr.Dataset(
            {
                "image": xr.DataArray(
                    np.zeros((2, 10, 10)),
                    dims=["c", "y", "x"],
                    coords={"c": ["DAPI", "GFP"]},
                ),
            },
        )
        ds.attrs["ome_channel_windows"] = [
            {"min": 0.0, "max": 65535.0, "start": 0.0, "end": 1500.0},
            {"min": 0.0, "max": 65535.0, "start": 0.0, "end": 2000.0},
        ]

        metadata = xarray_to_metadata(ds, preserve_original=False)

        channels = metadata["omero"]["channels"]
        assert channels[0]["window"]["end"] == 1500.0
        assert channels[1]["window"]["end"] == 2000.0


class TestRoundTrip:
    """Test bidirectional conversion (round-trip fidelity)."""

    def test_simple_roundtrip(self) -> None:
        """Test that metadata survives a round trip through xarray."""
        original_metadata = {
            "name": "test_image",
            "version": "0.4",
            "axes": [
                {"name": "c", "type": "channel"},
                {"name": "y", "type": "space", "unit": "micrometer"},
                {"name": "x", "type": "space", "unit": "micrometer"},
            ],
        }

        # Convert to attrs
        attrs = metadata_to_xarray_attrs(original_metadata)

        # Create a dataset with these attrs
        ds = xr.Dataset(
            {"image": xr.DataArray(np.zeros((2, 10, 10)), dims=["c", "y", "x"])},
        )
        ds.attrs.update(attrs)

        # Convert back to metadata
        reconstructed = xarray_to_metadata(ds, preserve_original=True)

        assert reconstructed == original_metadata

    def test_complex_metadata_roundtrip(self) -> None:
        """Test round trip with complex metadata including OMERO."""
        original_metadata = {
            "name": "complex_image",
            "version": "0.4",
            "axes": [
                {"name": "c", "type": "channel"},
                {"name": "z", "type": "space", "unit": "micrometer"},
                {"name": "y", "type": "space", "unit": "micrometer"},
                {"name": "x", "type": "space", "unit": "micrometer"},
            ],
            "datasets": [
                {"path": "0"},
                {"path": "1"},
                {"path": "2"},
            ],
            "omero": {
                "channels": [
                    {
                        "label": "DAPI",
                        "color": "0000FF",
                        "window": {"min": 0.0, "max": 65535.0, "start": 0.0, "end": 1500.0},
                    },
                    {
                        "label": "GFP",
                        "color": "00FF00",
                        "window": {"min": 0.0, "max": 65535.0, "start": 0.0, "end": 2000.0},
                    },
                ],
            },
        }

        # Convert to attrs
        attrs = metadata_to_xarray_attrs(original_metadata)

        # Create a dataset with channel labels in coordinates
        ds = xr.Dataset(
            {
                "image": xr.DataArray(
                    np.zeros((2, 5, 10, 10)),
                    dims=["c", "z", "y", "x"],
                    coords={"c": ["DAPI", "GFP"]},
                ),
            },
        )
        ds.attrs.update(attrs)

        # Convert back to metadata
        reconstructed = xarray_to_metadata(ds, preserve_original=True)

        assert reconstructed == original_metadata

    def test_unknown_fields_preserved(self) -> None:
        """Test that unknown/future metadata fields are preserved."""
        original_metadata = {
            "name": "test",
            "version": "0.5",  # Future version
            "future_field": "unknown_value",
            "complex_nested": {
                "level1": {
                    "level2": ["array", "of", "values"],
                },
            },
        }

        attrs = metadata_to_xarray_attrs(original_metadata)

        ds = xr.Dataset(
            {"image": xr.DataArray(np.zeros((10, 10)), dims=["y", "x"])},
        )
        ds.attrs.update(attrs)

        reconstructed = xarray_to_metadata(ds, preserve_original=True)

        # All unknown fields should be preserved exactly
        assert reconstructed["future_field"] == "unknown_value"
        assert reconstructed["complex_nested"]["level1"]["level2"] == ["array", "of", "values"]

    def test_numeric_channel_coords_roundtrip(self) -> None:
        """Test round trip with numeric channel coordinates (no labels)."""
        original_metadata = {
            "name": "numeric_channels",
            "version": "0.4",
            "axes": [
                {"name": "c", "type": "channel"},
                {"name": "y", "type": "space"},
                {"name": "x", "type": "space"},
            ],
        }

        attrs = metadata_to_xarray_attrs(original_metadata)

        # Dataset with numeric channel coordinates
        ds = xr.Dataset(
            {
                "image": xr.DataArray(
                    np.zeros((3, 10, 10)),
                    dims=["c", "y", "x"],
                    coords={"c": [0, 1, 2]},
                ),
            },
        )
        ds.attrs.update(attrs)

        reconstructed = xarray_to_metadata(ds, preserve_original=True)

        assert reconstructed == original_metadata
