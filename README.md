# osm2geojson

![Test package](https://github.com/rapkin/osm2geojson/workflows/Test%20package/badge.svg)
[![PyPI version](https://img.shields.io/pypi/v/osm2geojson.svg)](https://pypi.org/project/osm2geojson/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python versions](https://img.shields.io/pypi/pyversions/osm2geojson.svg)](https://pypi.org/project/osm2geojson/)

Convert OpenStreetMap and Overpass API data (JSON or XML) to GeoJSON or
[Shapely](https://shapely.readthedocs.io/) geometries.

Output closely matches [osmtogeojson](https://github.com/tyrasd/osmtogeojson)
(the JavaScript converter used by overpass-turbo), verified by a compatibility
suite.

**Highlights:**

- Assembles full geometries from raw OSM elements: multipolygon and boundary
  relations, routes, ways and POI nodes
- Accepts Overpass JSON, Overpass XML and plain OSM XML, including `out center`
  and `out bb` responses
- Produces a GeoJSON `FeatureCollection` or a list of Shapely shapes with
  properties — ready for GIS pipelines or rendering
- Ships a command-line tool (`osm2geojson`)
- Lightweight: the only dependencies are `shapely` and `requests`

## Installation

```bash
pip install osm2geojson
```

Requires Python 3.8+.

> **Try the 1.0 release candidate.** Version 1.0 changes the produced GeoJSON
> (matching [osmtogeojson](https://github.com/tyrasd/osmtogeojson)) and cleans
> up the API. Regular installs are unaffected until the final release; to test
> it now:
>
> ```bash
> pip install --pre --upgrade osm2geojson
> ```
>
> See the [CHANGELOG](CHANGELOG.md) and [MIGRATION_NOTES.md](MIGRATION_NOTES.md)
> for what changed - and please [report](https://github.com/rapkin/osm2geojson/issues)
> any unexpected output differences.

## Quick start

```python
import osm2geojson

# Fetch data from the Overpass API and convert it
xml = osm2geojson.overpass_call('rel(448930); out geom;')
geojson = osm2geojson.xml2geojson(xml)

# Or convert a local OSM/Overpass file
with open('data.osm', encoding='utf-8') as f:
    geojson = osm2geojson.xml2geojson(f.read())
```

### Command-line interface

```bash
osm2geojson map.osm map.geojson -i 2    # convert a file, pretty-printed
osm2geojson data.json -                 # Overpass JSON to stdout
```

Run `osm2geojson --help` for all options (input format autodetect/override,
indentation, custom area/polygon definitions, verbosity).

## API reference

### Conversion functions

| Function | Input | Output |
|----------|-------|--------|
| `json2geojson(data, **options)` | Overpass JSON (dict or str) | GeoJSON `FeatureCollection` |
| `xml2geojson(xml_str, **options)` | OSM/Overpass XML | GeoJSON `FeatureCollection` |
| `json2shapes(data, **options)` | Overpass JSON (dict or str) | list of Shape objects |
| `xml2shapes(xml_str, **options)` | OSM/Overpass XML | list of Shape objects |

All conversion functions accept these optional keyword-only parameters:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `filter_used_refs` | bool | `True` | Drop elements that are only used as parts of other features (`False` returns everything) |
| `log_level` | str | `None` | Set the library logger level for this call (`'DEBUG'`, `'INFO'`, ...); `None` leaves your logging configuration untouched |
| `area_keys` | dict | `None` | Custom area key definitions (defaults from `areaKeys.json`) |
| `polygon_features` | list | `None` | Custom polygon feature whitelist/blacklist (defaults from `polygon-features.json`) |
| `raise_on_failure` | bool | `False` | Raise `ConversionError` on geometry conversion failure instead of skipping the element |

Conversion functions never modify the data passed to them.

### Shape objects

`json2shapes`/`xml2shapes` return dictionaries pairing a Shapely geometry with
the OSM properties:

```python
{
    'shape': Point | LineString | Polygon | ...,  # Shapely geometry
    'properties': {
        'type': 'node' | 'way' | 'relation',
        'tags': { ... },
        'id': 123,
        ...
    }
}
```

Use `shape_to_feature(shape_obj, properties)` to turn a Shape object back into
a GeoJSON Feature.

### `overpass_call(query, **options)`

Execute an Overpass QL query and return the raw response text:

```python
result = osm2geojson.overpass_call('[out:json];node(50.746,7.154,50.748,7.157);out;')
```

Optional keyword-only parameters:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `endpoint` | str | overpass-api.de | Overpass API endpoint URL |
| `timeout` | float | `180` | Timeout in seconds for each HTTP request |
| `retries` | int | `5` | Retries on rate limiting (429), transient server errors (5xx), timeouts and connection errors; other errors fail immediately (`0` disables retrying) |
| `retry_delay` | float | `5` | Seconds to sleep between attempts |

## Examples

### Query the Overpass API and convert to GeoJSON

```python
import osm2geojson

query = """
[out:json];
(
  node["amenity"="restaurant"](50.746,7.154,50.748,7.157);
  way["amenity"="restaurant"](50.746,7.154,50.748,7.157);
);
out body geom;
"""

result = osm2geojson.overpass_call(query)
geojson = osm2geojson.json2geojson(result)
```

### Work with Shapely geometries

```python
import json
import osm2geojson

with open('overpass.json', encoding='utf-8') as f:
    data = json.load(f)

shapes = osm2geojson.json2shapes(data)

for shape_obj in shapes:
    geometry = shape_obj['shape']      # Shapely object
    osm_tags = shape_obj['properties']['tags']
    print(f"Type: {geometry.geom_type}, Tags: {osm_tags}")
```

## Upgrading to 1.0

Version 1.0 changed the produced GeoJSON (to match osmtogeojson) and made
converter options keyword-only. See the [CHANGELOG](CHANGELOG.md) for what
changed and [MIGRATION_NOTES.md](MIGRATION_NOTES.md) for upgrade help.

## Development

```bash
git clone https://github.com/rapkin/osm2geojson.git
cd osm2geojson

make setup       # one-command setup (installs deps + pre-commit hooks)
make all         # format, lint and test (do this before committing!)
```

Submodules (`osm-polygon-features`, `id-area-keys`) are optional - they are
only needed to regenerate the bundled JSON data (`update-osm-polygon-features.sh`).
Fetch them with `git submodule update --init` when needed.

- **[CONTRIBUTING.md](CONTRIBUTING.md)** - development setup, workflow and guidelines
- **[AI_AGENT_GUIDE.md](AI_AGENT_GUIDE.md)** - codebase guide for AI coding assistants
- **[RELEASE_GUIDE.md](RELEASE_GUIDE.md)** - release process for maintainers

## License

[MIT License](LICENSE)

## Credits

Developed by [rapkin](https://github.com/rapkin)

Uses data from:
- [osm-polygon-features](https://github.com/tyrasd/osm-polygon-features) - polygon feature definitions
- [id-area-keys](https://github.com/ideditor/id-area-keys) - area key definitions (extracted from the iD editor's [tagging schema](https://github.com/openstreetmap/id-tagging-schema))
