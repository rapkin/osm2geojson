# osm2geojson

![Test package](https://github.com/rapkin/osm2geojson/workflows/Test%20package/badge.svg)
[![PyPI version](https://img.shields.io/pypi/v/osm2geojson.svg)](https://pypi.org/project/osm2geojson/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python versions](https://img.shields.io/pypi/pyversions/osm2geojson.svg)](https://pypi.org/project/osm2geojson/)

Parse OSM and Overpass JSON/XML to GeoJSON with Python.

---

## Installation

```bash
pip install osm2geojson
```

---

## Usage

### Python API

Convert OSM/Overpass data to GeoJSON using one of four main functions:

```python
import osm2geojson

# From Overpass JSON
geojson = osm2geojson.json2geojson(overpass_json)

# From OSM/Overpass XML
geojson = osm2geojson.xml2geojson(osm_xml)

# To Shape objects (Shapely geometries + properties)
shapes = osm2geojson.json2shapes(overpass_json)
shapes = osm2geojson.xml2shapes(osm_xml)
```

### Command-Line Interface

After installation, use as a command-line tool:

```bash
osm2geojson --help
# or
python -m osm2geojson --help
```

---

## API Reference

### Main Functions

#### `json2geojson(data, **options)`
Convert Overpass JSON to GeoJSON FeatureCollection.

#### `xml2geojson(xml_str, **options)`
Convert OSM/Overpass XML to GeoJSON FeatureCollection.

#### `json2shapes(data, **options)`
Convert Overpass JSON to Shape objects (Shapely geometry + properties).

#### `xml2shapes(xml_str, **options)`
Convert OSM/Overpass XML to Shape objects.

### Options

All conversion functions accept these optional keyword-only parameters:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `filter_used_refs` | bool | `True` | Filter unused references (False returns all geometry) |
| `log_level` | str | `None` | Set the library logger level for this call (`'DEBUG'`, `'INFO'`, ...); `None` leaves your logging configuration untouched |
| `area_keys` | dict | `None` | Custom area key definitions (defaults from `areaKeys.json`) |
| `polygon_features` | list | `None` | Custom polygon feature whitelist/blacklist (defaults from `polygon-features.json`) |
| `raise_on_failure` | bool | `False` | Raise `ConversionError` on geometry conversion failure |

Conversion functions never modify the data passed to them.

### Helper Functions

#### `overpass_call(query, **options)`
Execute Overpass API query.

```python
result = osm2geojson.overpass_call('[out:json];node(50.746,7.154,50.748,7.157);out;')
```

Optional keyword-only parameters:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `endpoint` | str | overpass-api.de | Overpass API endpoint URL |
| `timeout` | float | `180` | Timeout in seconds for each HTTP request |
| `retries` | int | `5` | Retries after a failed attempt (`0` disables retrying) |
| `retry_delay` | float | `5` | Seconds to sleep between attempts |

#### `shape_to_feature(shape_obj, properties)`
Convert Shape object to GeoJSON Feature.

```python
feature = osm2geojson.shape_to_feature(
    shape_obj=shapely_shape_object,
    properties={'custom': 'property'}
)
```

### Shape Objects

Shape objects are dictionaries containing Shapely geometry and OSM properties:

```python
{
    'shape': Point | LineString | Polygon,  # Shapely geometry
    'properties': {
        'type': 'node' | 'way' | 'relation',
        'tags': { ... },                     # OSM tags
        'id': 123,
        ...
    }
}
```

---

## Examples

### Convert OSM XML to GeoJSON

```python
import osm2geojson

with open('data.osm', 'r', encoding='utf-8') as f:
    xml = f.read()

geojson = osm2geojson.xml2geojson(xml, filter_used_refs=False, log_level='INFO')
# Returns: { "type": "FeatureCollection", "features": [ ... ] }
```

### Convert Overpass JSON to Shapes

```python
import json
import osm2geojson

with open('overpass.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

shapes = osm2geojson.json2shapes(data)
# Returns: [ { "shape": <Shapely geometry>, "properties": {...} }, ... ]

# Access geometry and properties
for shape_obj in shapes:
    geometry = shape_obj['shape']      # Shapely object
    osm_tags = shape_obj['properties']['tags']
    print(f"Type: {geometry.geom_type}, Tags: {osm_tags}")
```

### Query Overpass API Directly

```python
import osm2geojson

# Overpass QL query
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

---

## Development

### Quick Start

```bash
git clone https://github.com/rapkin/osm2geojson.git
cd osm2geojson

# One-command setup (installs deps + pre-commit hooks)
make setup
```

Submodules (`osm-polygon-features`, `id-area-keys`) are optional - they are
only needed to regenerate the bundled JSON data (`update-osm-polygon-features.sh`).
Fetch them with `git submodule update --init` when needed.

### Development Workflow

```bash
make format      # Auto-format code with Ruff
make lint        # Check code quality
make test        # Run tests with pytest
make all         # Run all checks (do this before committing!)
```

### Run Specific Tests

```bash
# Single test (unittest-style class)
pytest tests/test_main.py::TestOsm2GeoJsonMethods::test_barrier_wall -vv

# Test file
pytest tests/test_main.py -vv

# By pattern
pytest -k barrier -vv

# With coverage
make test-coverage
```

### Update Polygon Features

```bash
./update-osm-polygon-features.sh
```

### Releasing

See [RELEASE_GUIDE.md](RELEASE_GUIDE.md) for the release process.

Quick version bump:
```bash
./bump_version.sh 0.3.0  # Updates version, commits, and tags
git push origin master --tags
# Then create GitHub Release to publish to PyPI
```

### Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for detailed development guidelines.

---

## Documentation

- **[CONTRIBUTING.md](CONTRIBUTING.md)** - Development setup, workflow, and guidelines
- **[AI_AGENT_GUIDE.md](AI_AGENT_GUIDE.md)** - Comprehensive guide for AI coding assistants
- **[MIGRATION_NOTES.md](MIGRATION_NOTES.md)** - Guide for migrating from old setup
- **[RELEASE_GUIDE.md](RELEASE_GUIDE.md)** - Release process for maintainers

---

## Project Structure

```
osm2geojson/
├── osm2geojson/          # Main package
│   ├── main.py           # Core conversion logic
│   ├── parse_xml.py      # XML parsing
│   ├── helpers.py        # Helper functions
│   └── __main__.py       # CLI interface
├── tests/                # Test suite
├── pyproject.toml        # Project config (deps, tools)
├── Makefile              # Development commands
└── README.md             # This file
```

---

## Technology Stack

- **Python**: 3.8+
- **Shapely**: Geometric operations
- **Requests**: Overpass API calls
- **Ruff**: Fast linting & formatting
- **pytest**: Modern testing framework
- **mypy**: Type checking

---

## License

[MIT License](LICENSE)

---

## Credits

Developed by [rapkin](https://github.com/rapkin)

Uses data from:
- [osm-polygon-features](https://github.com/tyrasd/osm-polygon-features) - Polygon feature definitions
- [id-area-keys](https://github.com/openstreetmap/id-tagging-schema) - Area key definitions

