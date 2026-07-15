import json
import os
import unittest

from osm2geojson import overpass_call, parse_xml, read_data_file


LIVE_TESTS = os.environ.get("OSM2GEOJSON_LIVE_TESTS")


class TestParseXmlMethods(unittest.TestCase):
    def test_empty_tag(self):
        """
        Test parsing of empty <osm> tag
        """
        xml = read_data_file("empty.osm")
        data = parse_xml(xml)

        self.assertIsInstance(data, dict)
        # Use version 0.6 as default
        self.assertEqual(data["version"], 0.6)
        self.assertEqual(data["elements"], [])

    def test_node(self):
        """
        Test parsing node
        """
        xml = read_data_file("node.osm")
        data = parse_xml(xml)

        self.assertIsInstance(data, dict)
        self.assertIsInstance(data["elements"], list)
        self.assertEqual(len(data["elements"]), 1)

        node = data["elements"][0]
        self.assertIsInstance(node, dict)
        self.assertEqual(node["type"], "node")
        self.assertEqual(node["id"], 1)
        self.assertAlmostEqual(node["lat"], 1.234)
        self.assertAlmostEqual(node["lon"], 4.321)

    def test_way(self):
        """
        Test parsing way
        """
        xml = read_data_file("way.osm")
        data = parse_xml(xml)

        self.assertIsInstance(data, dict)
        self.assertIsInstance(data["elements"], list)
        self.assertEqual(len(data["elements"]), 4)

        way = data["elements"][0]

        self.assertIsInstance(way, dict)
        self.assertEqual(way["type"], "way")
        self.assertEqual(way["id"], 1)
        self.assertIsInstance(way["nodes"], list)
        self.assertEqual(way["nodes"], [2, 3, 4])

    def test_relation(self):
        """
        Test parsing relation
        """
        xml = read_data_file("relation.osm")
        data = parse_xml(xml)

        self.assertIsInstance(data, dict)
        self.assertIsInstance(data["elements"], list)
        self.assertEqual(len(data["elements"]), 10)

        relation = data["elements"][0]

        self.assertIsInstance(relation, dict)
        self.assertEqual(relation["type"], "relation")
        self.assertEqual(relation["id"], 1)
        self.assertIsInstance(relation["members"], list)
        self.assertEqual(len(relation["members"]), 2)
        self.assertEqual(relation["tags"], {"type": "multipolygon"})

    def test_map(self):
        """
        Test parsing of usual map
        """
        xml = read_data_file("map.osm")
        data = parse_xml(xml)

        self.assertIsInstance(data, dict)
        self.assertEqual(data["version"], 0.6)

    def test_all_files(self):
        """
        Test parsing of all files and compare with json version
        """
        for name in ["empty", "node", "way", "map", "relation"]:
            xml_data = read_data_file(name + ".osm")
            json_data = read_data_file(name + ".json")
            parsed_json = parse_xml(xml_data)
            saved_json = json.loads(json_data)

            if "version" not in saved_json:
                del parsed_json["version"]

            self.assertDictEqual(saved_json, parsed_json)

    @unittest.skipUnless(
        LIVE_TESTS, "slow live test (8 Overpass API calls); set OSM2GEOJSON_LIVE_TESTS=1 to run"
    )
    def test_overpass_queries(self):
        """
        Test several queries to overpass
        """
        queries = [
            "rel(448930); out geom;",
            "rel(448930); out meta;",
            "rel(448930); out bb;",
            "rel(448930); out count;",
        ]

        for query in queries:
            print("Test query:", query)
            query_json = "[out:json];" + query
            data_xml = overpass_call(query)
            data_json = overpass_call(query_json)
            overpass_json = json.loads(data_json)
            parsed_json = parse_xml(data_xml)
            # Ignore different time for queries
            del overpass_json["osm3s"]["timestamp_osm_base"]
            del parsed_json["osm3s"]["timestamp_osm_base"]
            # Ignore generator (overpass use different versions of generators?)
            del overpass_json["generator"]
            del parsed_json["generator"]
            self.assertDictEqual(overpass_json, parsed_json)


if __name__ == "__main__":
    unittest.main()
