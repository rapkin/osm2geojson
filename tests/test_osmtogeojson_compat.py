"""Compatibility suite against osmtogeojson (the JS converter used by overpass-turbo).

Fixtures in tests/data/osmtogeojson-fixtures.json were extracted from
osmtogeojson 3.0.0-beta.5's own test suite (test/osm.test.js): every test case's
input was run through the real JS library and the (input, output) pair recorded
(see tests/tools/extract_osmtogeojson_fixtures.js). Cases exercising
osmtogeojson-specific API options (featureCallback, flatProperties,
custom deduplicators/polygon detection) are excluded.

Outputs are compared semantically, not textually:
  * features are matched by (element type, id) - ids normalized to str
  * tags must match exactly, other properties are library-specific
    (osmtogeojson nests meta/relations; osm2geojson inlines meta keys)
  * geometry is compared topologically with shapely, treating a Polygon and a
    single-polygon MultiPolygon (etc.) as equal, ignoring ring/vertex order

Known, intentional differences (cases listed in KNOWN_DIFFERENCES):
  * degenerate geometry: osm2geojson guarantees valid GeoJSON geometry and
    drops zero-area rings, unclosed degenerate rings and null coordinates,
    which osmtogeojson emits verbatim
  * relations whose type is not multipolygon/boundary/route/waterway (e.g.
    associatedStreet or no type at all) still get a merged MultiLineString
    feature in osm2geojson; osmtogeojson emits no feature for them
  * member ways carrying inline geometry ("out geom") are still filtered by
    filter_used_refs when they have no interesting tags; osmtogeojson skips
    that filtering entirely for full-geometry responses and emits duplicates
"""

import json
import unittest

from shapely.geometry import shape

from osm2geojson import json2geojson, xml2geojson
from tests.utils import read_data_file


# case name -> list of expected difference descriptions (see _compare)
KNOWN_DIFFERENCES = {
    "osm (json) / relations and id-spaces": [
        # relation 1 has no type tag; py emits a MultiLineString feature for it
        "call0: extra in py: ('relation', '1') (py geometry: ['MultiLineString'])",
    ],
    "defaults / interesting objects: relation members": [
        # type=fancy relation; py emits a MultiLineString feature for it
        "call0: extra in py: ('relation', '4294968148') (py geometry: ['MultiLineString'])",
    ],
    "osm (json) / meta data": [
        # degenerate ways (nodes [1,1,1,1]); py refuses to build the zero-area
        # multipolygon, js emits it and attributes it old-style to way 2
        "call1: missing in py: ('relation', '1') (js geometry: ['MultiPolygon'])",
        "call1: geometry differs for ('way', '2'): py=LineString js=Polygon",
    ],
    "osm (json) / multipolygon: non-trivial ring building": [
        # all nodes are collinear - the assembled ring has zero area
        "call0: missing in py: ('relation', '1') (js geometry: ['Polygon'])",
        "call1: missing in py: ('relation', '1') (js geometry: ['Polygon'])",
    ],
    "osm (json) / multipolygon: unclosed ring": [
        # collinear nodes again; js even emits an unclosed ring as a Polygon
        "call0: geometry differs for ('relation', '1'): py=MultiPolygon js=Polygon",
        "call1: missing in py: ('relation', '1') (js geometry: ['Polygon'])",
    ],
    "other / sideeffects": [
        # way 1 references nodes without coordinates; js emits a LineString
        # containing literal null coordinates (invalid GeoJSON), py drops it
        "call0: missing in py: ('way', '1') (js geometry: ['LineString'])",
    ],
}


def _norm_tags(props):
    return props.get("tags") or {}


def _feature_key(feature):
    props = feature["properties"]
    return (props.get("type"), str(props.get("id")))


def _unwrap(geom):
    if geom.geom_type in ("MultiPolygon", "MultiLineString", "MultiPoint") and len(geom.geoms) == 1:
        return geom.geoms[0]
    return geom


def _geom_equal(g1, g2):
    if g1 is None or g2 is None:
        return g1 is g2
    if g1 == g2:
        # structurally identical GeoJSON; also dodges GEOS-version-dependent
        # .equals() results on degenerate geometry (e.g. zero-length lines)
        return True
    s1, s2 = shape(g1), shape(g2)
    if s1.geom_type != s2.geom_type:
        s1, s2 = _unwrap(s1), _unwrap(s2)
    return s1.equals(s2)


def _index(features):
    idx = {}
    for feature in features:
        idx.setdefault(_feature_key(feature), []).append(feature)
    return idx


def _compare(py_result, js_output):
    """Return a list of difference descriptions (empty = semantically equal)."""
    diffs = []
    py_idx = _index(py_result["features"])
    js_idx = _index(js_output["features"])

    for key in sorted(set(py_idx) | set(js_idx), key=str):
        py_feats = py_idx.get(key, [])
        js_feats = js_idx.get(key, [])
        if not py_feats:
            geoms = [f["geometry"]["type"] if f.get("geometry") else None for f in js_feats]
            diffs.append(f"missing in py: {key} (js geometry: {geoms})")
            continue
        if not js_feats:
            geoms = [f["geometry"]["type"] if f.get("geometry") else None for f in py_feats]
            diffs.append(f"extra in py: {key} (py geometry: {geoms})")
            continue
        if len(py_feats) != len(js_feats):
            diffs.append(f"count mismatch for {key}: py={len(py_feats)} js={len(js_feats)}")
            continue
        for py_feat, js_feat in zip(py_feats, js_feats):
            py_tags, js_tags = _norm_tags(py_feat["properties"]), _norm_tags(js_feat["properties"])
            if py_tags != js_tags:
                diffs.append(f"tags differ for {key}: py={py_tags} js={js_tags}")
            if not _geom_equal(py_feat.get("geometry"), js_feat.get("geometry")):
                py_type = py_feat["geometry"]["type"] if py_feat.get("geometry") else None
                js_type = js_feat["geometry"]["type"] if js_feat.get("geometry") else None
                diffs.append(f"geometry differs for {key}: py={py_type} js={js_type}")
    return diffs


def _run_case(call):
    if call["input_type"] == "xml":
        return xml2geojson(call["input"])
    # no defensive copy: the fixtures double as a canary for the guarantee
    # that json2geojson does not mutate its input
    return json2geojson(call["input"])


class TestOsmtogeojsonCompat(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = json.loads(read_data_file("osmtogeojson-fixtures.json"))

    def test_compatibility(self):
        for case in self.cases:
            with self.subTest(case=case["name"]):
                diffs = []
                for i, call in enumerate(case["calls"]):
                    for diff in _compare(_run_case(call), call["output"]):
                        diffs.append(f"call{i}: {diff}")
                expected = KNOWN_DIFFERENCES.get(case["name"], [])
                self.assertEqual(
                    sorted(diffs),
                    sorted(expected),
                    f"unexpected divergence from osmtogeojson in: {case['name']}",
                )

    def test_all_known_differences_still_exist(self):
        names = {case["name"] for case in self.cases}
        for name in KNOWN_DIFFERENCES:
            self.assertIn(name, names, f"stale KNOWN_DIFFERENCES entry: {name}")


if __name__ == "__main__":
    unittest.main()
