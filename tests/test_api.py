"""Tests for the public API contract introduced in 1.0.

Covers: no input mutation, no internal keys in results, ConversionError,
keyword-only converter arguments, and the trimmed public surface.
"""

import copy
import json

import pytest

import osm2geojson
from osm2geojson import ConversionError, json2geojson, json2shapes


SQUARE_NODES = [
    {"type": "node", "id": 1, "lat": 0.0, "lon": 0.0},
    {"type": "node", "id": 2, "lat": 0.0, "lon": 1.0},
    {"type": "node", "id": 3, "lat": 1.0, "lon": 1.0},
    {"type": "node", "id": 4, "lat": 1.0, "lon": 0.0},
]


def old_style_multipolygon_data():
    """A relation carrying only type=multipolygon; tags live on the outer way."""
    return {
        "elements": [
            *SQUARE_NODES,
            {
                "type": "way",
                "id": 10,
                "nodes": [1, 2, 3, 4, 1],
                "tags": {"landuse": "forest"},
            },
            {
                "type": "relation",
                "id": 100,
                "tags": {"type": "multipolygon"},
                "members": [{"type": "way", "ref": 10, "role": "outer"}],
            },
        ]
    }


def test_input_is_not_mutated():
    data = old_style_multipolygon_data()
    snapshot = copy.deepcopy(data)
    json2geojson(data)
    json2shapes(data)
    assert data == snapshot


def test_no_internal_keys_in_shapes():
    shapes = json2shapes(old_style_multipolygon_data())
    assert shapes, "expected at least one shape"
    for shape in shapes:
        assert set(shape) <= {"shape", "properties"}


def test_conversion_error_on_failure():
    broken = {
        "elements": [
            {"type": "way", "id": 1, "nodes": [1, 2], "tags": {"highway": "road"}},
        ]
    }
    with pytest.raises(ConversionError):
        json2geojson(broken, raise_on_failure=True)
    # and silent degradation without the flag
    result = json2geojson(broken)
    assert result["features"] == []


def test_converter_options_are_keyword_only():
    data = json.dumps({"elements": []})
    with pytest.raises(TypeError):
        json2geojson(data, False)


def test_inline_member_node_shared_by_relations_is_one_feature():
    """A node existing only inline in two relations must not be duplicated."""
    member = {"type": "node", "ref": 7, "role": "admin_centre", "lat": 0.5, "lon": 0.5}
    data = {
        "elements": [
            {"type": "relation", "id": 1, "tags": {"type": "site"}, "members": [dict(member)]},
            {"type": "relation", "id": 2, "tags": {"type": "site"}, "members": [dict(member)]},
        ]
    }
    features = json2geojson(data)["features"]
    points = [f for f in features if f["properties"].get("type") == "node"]
    assert len(points) == 1
    assert points[0]["properties"]["id"] == 7


def test_public_surface():
    assert "read_data_file" not in osm2geojson.__all__
    assert not hasattr(osm2geojson, "read_data_file")
    assert "ConversionError" in osm2geojson.__all__
