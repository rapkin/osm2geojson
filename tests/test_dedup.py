"""Tests for deduplicate_elements (merging repeated Overpass elements)."""

from osm2geojson import json2geojson
from osm2geojson.main import deduplicate_elements


def way(**fields):
    return {"type": "way", "id": 1, **fields}


GEOMETRY = [{"lat": 50.0, "lon": 7.0}, {"lat": 50.1, "lon": 7.1}]


def test_split_copies_keep_geometry_and_tags():
    """Tags and geometry split over two copies (e.g. "out tags;" + "out skel
    geom;") must merge into one convertible element, not lose the geometry."""
    tags_copy = way(version=2, tags={"highway": "service"})
    geom_copy = way(nodes=[10, 11], geometry=GEOMETRY)

    for elements in ([tags_copy, geom_copy], [geom_copy, tags_copy]):
        result = json2geojson({"elements": elements})
        assert len(result["features"]) == 1, elements
        feature = result["features"][0]
        assert feature["geometry"]["type"] == "LineString"
        assert feature["properties"]["tags"] == {"highway": "service"}


def test_winner_fields_beat_loser_fields():
    merged = deduplicate_elements(
        [way(version=1, tags={"name": "old"}), way(version=2, tags={"name": "new"})]
    )
    assert merged == [way(version=2, tags={"name": "new"})]


def test_same_version_tags_are_merged():
    merged = deduplicate_elements(
        [way(version=3, tags={"a": "1"}), way(version=3, tags={"b": "2"})]
    )
    assert merged[0]["tags"] == {"a": "1", "b": "2"}


def test_distinct_elements_are_kept_in_order():
    elements = [
        {"type": "node", "id": 1, "lat": 50.0, "lon": 7.0},
        {"type": "way", "id": 1, "nodes": [1]},
        {"type": "node", "id": 2, "lat": 50.1, "lon": 7.1},
    ]
    assert deduplicate_elements(elements) == elements


def test_elements_without_id_are_kept():
    elements = [{"foo": "bar"}, {"foo": "baz"}]
    assert deduplicate_elements(elements) == elements
