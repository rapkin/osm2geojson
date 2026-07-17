"""osm2geojson - Parse OSM and Overpass JSON with Python.

This library provides functions to convert OpenStreetMap (OSM) data
and Overpass API responses into GeoJSON format.

Main functions:
- xml2geojson: Convert OSM XML to GeoJSON
- json2geojson: Convert Overpass JSON to GeoJSON
- xml2shapes: Convert OSM XML to Shape objects
- json2shapes: Convert Overpass JSON to Shape objects
- shape_to_feature: Convert a Shape object to a GeoJSON Feature
- overpass_call: Fetch data from the Overpass API
- ConversionError: Raised on conversion failure (with raise_on_failure=True)

Logging: the library logs through the "osm2geojson" logger and never
configures logging itself - enable diagnostics with
logging.getLogger("osm2geojson").setLevel(...) in your application.
"""

import logging

from .helpers import overpass_call
from .main import (
    ConversionError,
    json2geojson,
    json2shapes,
    shape_to_feature,
    xml2geojson,
    xml2shapes,
)
from .parse_xml import parse as parse_xml


logging.getLogger(__name__).addHandler(logging.NullHandler())

# Version is defined in pyproject.toml
try:
    from importlib.metadata import version

    __version__ = version("osm2geojson")
except Exception:
    __version__ = "unknown"
__all__ = [
    "ConversionError",
    "json2geojson",
    "json2shapes",
    "overpass_call",
    "parse_xml",
    "shape_to_feature",
    "xml2geojson",
    "xml2shapes",
]
