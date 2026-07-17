"""Tests for issue #54: OSM relations with non-consecutive role ordering."""

import osm2geojson
from tests.utils import read_data_file


def test_issue_54_staffordshire_multipolygon():
    """Test that Staffordshire relation with unusual ordering converts correctly.

    The OSM relation 195444 (Staffordshire) has members ordered as:
    - Many outer ways
    - Inner ways
    - More outer ways at the end

    This unusual ordering should still produce a single outer polygon with inner holes,
    not multiple outer polygons.
    """
    data = read_data_file("issue-54-staffordshire.osm")
    geojson = osm2geojson.xml2geojson(data, filter_used_refs=False)

    # Should have exactly one relation feature (the county boundary); member nodes
    # (e.g. admin_centre) come along as separate Point features
    relations = [f for f in geojson["features"] if f["properties"]["type"] == "relation"]
    assert len(relations) == 1, "Should have exactly one relation feature"

    feature = relations[0]
    assert feature["geometry"]["type"] == "MultiPolygon"

    # Get the coordinates
    coordinates = feature["geometry"]["coordinates"]

    # Each polygon in a MultiPolygon has format: [exterior, hole1, hole2, ...]
    # Count total number of outer rings and holes across all polygons
    total_outers = len(coordinates)  # Each polygon in MultiPolygon is one outer
    total_holes = sum(len(polygon) - 1 for polygon in coordinates)  # -1 because first is outer

    # Verified against osmtogeojson JS reference implementation:
    # - osmtogeojson produces: 1 Polygon with 1 outer + 1 hole
    # - Our implementation produces: 1 MultiPolygon with 1 outer + 1 hole
    # (MultiPolygon is correct for relations, just a formatting difference)

    # The bug would create multiple outers (one per groupby group)
    # With the fix, we should have exactly 1 outer
    assert total_outers == 1, (
        f"Expected exactly 1 outer polygon, got {total_outers}. "
        f"The bug would create 3+ outers due to role grouping: "
        f"(outer group 1, inner group, outer group 2)."
    )

    # Based on osmtogeojson reference, should have 1 hole
    assert total_holes == 1, f"Expected 1 hole (verified with osmtogeojson), got {total_holes}"

    print(f"✓ Staffordshire: {total_outers} outer(s) with {total_holes} hole(s)")
