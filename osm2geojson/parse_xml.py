"""XML parsing utilities for OSM data."""

from typing import Any, List, Optional, Tuple
from xml.etree import ElementTree


default_types = ["node", "way", "relation", "member", "nd"]
optional_meta_fields = ["timestamp", "version:int", "changeset:int", "user", "uid:int"]


def parse_key(key: str) -> Tuple[str, str]:
    """Parse a field key and its type specification.

    Args:
        key: Field key, optionally with type suffix (e.g., 'id:int').

    Returns:
        Tuple of (field_name, type_string).
    """
    t = "string"
    parts = key.split(":")
    if len(parts) > 1:
        t = parts[1]
    return parts[0], t


def to_type(v: str, t: str) -> Any:
    """Convert a string value to the specified type.

    Args:
        v: Value to convert.
        t: Type string ('string', 'int', 'float').

    Returns:
        Converted value.
    """
    if t == "string":
        return str(v)
    if t == "int":
        return int(v)
    if t == "float":
        return float(v)
    return v


def with_meta_fields(fields: Optional[List[str]] = None) -> List[str]:
    """Add optional metadata fields to the given field list.

    Args:
        fields: Initial list of fields.

    Returns:
        Combined list with metadata fields.
    """
    fields = fields or []
    for field in optional_meta_fields:
        if field not in fields:
            fields.append(field)
    return fields


def copy_fields(
    node: ElementTree.Element,
    base: List[str],
    optional: Optional[List[str]] = None,
) -> dict:
    """Extract fields from an XML element into a dictionary.

    Args:
        node: XML element to extract from.
        base: Required field names.
        optional: Optional field names.

    Returns:
        Dictionary of extracted field values.
    """
    optional = optional or []
    obj = {}
    for key in base:
        key, t = parse_key(key)
        if key not in node.attrib:
            print(key, "not found in", node.tag, node.attrib)
        obj[key] = to_type(node.attrib[key], t)
    for key in optional:
        key, t = parse_key(key)
        if key in node.attrib:
            obj[key] = to_type(node.attrib[key], t)
    return obj


def filter_items_by_type(items: List[dict], types: List[str]) -> List[dict]:
    """Filter items by their type field.

    Args:
        items: List of item dictionaries.
        types: List of valid type strings.

    Returns:
        Filtered list of items.
    """
    return [i for i in items if i["type"] in types]


def tags_to_obj(tags: List[dict]) -> dict:
    """Convert a list of tag dictionaries to a single dictionary.

    Args:
        tags: List of tag dictionaries with 'k' and 'v' keys.

    Returns:
        Dictionary mapping tag keys to values.
    """
    return {tag["k"]: tag["v"] for tag in tags}


def parse_bounds(node: ElementTree.Element) -> dict:
    """Parse a bounds XML element.

    Args:
        node: XML element to parse.

    Returns:
        Dictionary with bounds coordinates.
    """
    return copy_fields(node, ["minlat:float", "minlon:float", "maxlat:float", "maxlon:float"])


def parse_center(node: ElementTree.Element) -> Optional[dict]:
    """Parse the center child of an element ("out center" responses).

    Args:
        node: XML element whose children to search.

    Returns:
        Dictionary with lat/lon, or None if there is no center child.
    """
    center = node.find("center")
    if center is None:
        return None
    return copy_fields(center, ["lat:float", "lon:float"])


def parse_count(node: ElementTree.Element) -> dict:
    """Parse a count XML element.

    Args:
        node: XML element to parse.

    Returns:
        Dictionary with count information.
    """
    _bounds, tags, _empty, _unhandled = parse_xml_node(node, [])
    item = copy_fields(node, ["id:int"])
    item["type"] = "count"
    if len(tags) > 0:
        item["tags"] = tags_to_obj(tags)
    return item


def parse_tag(node: ElementTree.Element) -> dict:
    """Parse a tag XML element.

    Args:
        node: XML element to parse.

    Returns:
        Dictionary with 'k' and 'v' keys.
    """
    return copy_fields(node, ["k", "v"])


def parse_nd(node: ElementTree.Element) -> dict:
    """Parse a node reference (nd) XML element.

    Args:
        node: XML element to parse.

    Returns:
        Dictionary with node reference information.
    """
    return copy_fields(node, [], ["ref:int", "lat:float", "lon:float"])


def parse_node(node: ElementTree.Element) -> dict:
    """Parse a node XML element.

    Args:
        node: XML element to parse.

    Returns:
        Dictionary with node information.
    """
    _bounds, tags, _items, _unhandled = parse_xml_node(node)
    item = copy_fields(
        node, [], with_meta_fields(["role", "id:int", "ref:int", "lat:float", "lon:float"])
    )
    item["type"] = "node"
    if len(tags) > 0:
        item["tags"] = tags_to_obj(tags)
    return item


def parse_way(node: ElementTree.Element) -> dict:
    """Parse a way XML element.

    Args:
        node: XML element to parse.

    Returns:
        Dictionary with way information.
    """
    bounds, tags, nds, _unhandled = parse_xml_node(node, ["nd"])
    geometry = []
    nodes = []
    for nd in nds:
        if "ref" in nd and "lat" not in nd and "lon" not in nd:
            nodes.append(nd["ref"])
        else:
            geometry.append(nd)

    way = copy_fields(node, [], with_meta_fields(["ref:int", "id:int", "role"]))
    way["type"] = "way"
    if len(tags) > 0:
        way["tags"] = tags_to_obj(tags)
    if geometry:
        way["geometry"] = geometry
    if nodes:
        way["nodes"] = nodes
    if bounds is not None:
        way["bounds"] = bounds
    center = parse_center(node)
    if center is not None:
        way["center"] = center
    return way


def parse_relation(node: ElementTree.Element) -> dict:
    """Parse a relation XML element.

    Args:
        node: XML element to parse.

    Returns:
        Dictionary with relation information.
    """
    bounds, tags, members, _unhandled = parse_xml_node(node, ["member"])

    relation = copy_fields(node, [], with_meta_fields(["id:int", "ref:int", "role"]))
    relation["type"] = "relation"
    if len(members) > 0:
        relation["members"] = members
    if bounds is not None:
        relation["bounds"] = bounds
    center = parse_center(node)
    if center is not None:
        relation["center"] = center
    if len(tags) > 0:
        relation["tags"] = tags_to_obj(tags)
    return relation


def format_ojson(elements: List[dict], unhandled: List[ElementTree.Element]) -> dict:
    """Format parsed elements into Overpass JSON format.

    Args:
        elements: List of parsed OSM elements.
        unhandled: List of unhandled XML elements.

    Returns:
        Dictionary in Overpass JSON format.
    """
    version = 0.6
    generator = None
    timestamp_osm_base = None
    copyright = None

    for node in unhandled:
        if node.tag == "meta" and "osm_base" in node.attrib:
            timestamp_osm_base = node.attrib["osm_base"]
        elif node.tag == "note":
            copyright = node.text
        elif node.tag == "osm":
            if "version" in node.attrib:
                version = float(node.attrib["version"])
            if "generator" in node.attrib:
                generator = node.attrib["generator"]

    item = {"version": version, "elements": elements}

    if generator is not None:
        item["generator"] = generator
    if copyright is not None:
        item.setdefault("osm3s", {})["copyright"] = copyright
    if timestamp_osm_base is not None:
        item.setdefault("osm3s", {})["timestamp_osm_base"] = timestamp_osm_base

    return item


def parse(xml_str: str) -> Optional[dict]:
    """Parse OSM XML string into Overpass JSON format.

    Args:
        xml_str: XML string to parse.

    Returns:
        Dictionary in Overpass JSON format, or None if parsing fails.
    """
    root = ElementTree.fromstring(xml_str)
    if root.tag != "osm":
        print("OSM root node not found!")
        return None

    _bounds, _tags, elements, unhandled = parse_xml_node(root, ["node", "way", "relation", "count"])
    unhandled.append(root)
    return format_ojson(elements, unhandled)


def parse_node_type(node: ElementTree.Element, node_type: str) -> Optional[dict]:
    """Parse an XML element based on its type.

    Args:
        node: XML element to parse.
        node_type: Type of the node.

    Returns:
        Parsed dictionary, or None if type is unhandled.
    """
    if node_type == "bounds":
        return parse_bounds(node)

    if node_type == "tag":
        return parse_tag(node)

    if node_type == "node":
        return parse_node(node)

    if node_type == "way":
        return parse_way(node)

    if node_type == "relation":
        return parse_relation(node)

    if node_type == "member":
        return parse_node_type(node, node.attrib["type"])

    if node_type == "nd":
        return parse_nd(node)

    print("Unhandled node type", node_type)
    return None


def parse_xml_node(
    root: ElementTree.Element, node_types: Optional[List[str]] = None
) -> Tuple[Optional[dict], List[dict], List[dict], List[ElementTree.Element]]:
    """Parse an XML node and its children.

    Args:
        root: Root XML element to parse.
        node_types: List of node types to extract.

    Returns:
        Tuple of (bounds, tags, items, unhandled).
    """
    node_types = node_types or default_types
    bounds = None
    count = None
    tags = []
    items = []
    unhandled = []

    for child in root:
        if child.tag == "bounds":
            if bounds is not None:
                print("Node bounds should be unique")
            bounds = parse_bounds(child)
        elif child.tag == "count":
            if count is not None:
                print("Node count should be unique")
            count = parse_count(child)
        else:
            if child.tag == "tag":
                tags.append(parse_tag(child))
                continue

            if child.tag not in default_types:
                unhandled.append(child)
                continue

            if child.tag in node_types:
                items.append(parse_node_type(child, child.tag))

    if "count" in node_types and count is not None:
        items.append(count)
    return bounds, tags, items, unhandled
