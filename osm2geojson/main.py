"""Main module for converting OSM data to GeoJSON format.

This module provides the core functionality for converting OpenStreetMap (OSM)
and Overpass API data into GeoJSON format, handling various geometry types
including nodes, ways, and relations.
"""

import json
import logging
import os
from pprint import pformat
from typing import Optional

from shapely.geometry import (
    GeometryCollection,
    LineString,
    MultiLineString,
    MultiPolygon,
    Point,
    Polygon,
    mapping,
)
from shapely.geometry.polygon import orient
from shapely.ops import linemerge, unary_union

from .parse_xml import parse as parse_xml


logger = logging.getLogger(__name__)
DEFAULT_POLYGON_FEATURES_FILE = os.path.join(os.path.dirname(__file__), "polygon-features.json")
DEFAULT_AREA_KEYS_FILE = os.path.join(os.path.dirname(__file__), "areaKeys.json")

if os.path.exists(DEFAULT_POLYGON_FEATURES_FILE):
    with open(DEFAULT_POLYGON_FEATURES_FILE) as f:
        _default_polygon_features = json.load(f)
else:
    logger.warning("Default polygon features file not found, using empty filter")
    _default_polygon_features = []

if os.path.exists(DEFAULT_AREA_KEYS_FILE):
    with open(DEFAULT_AREA_KEYS_FILE) as f:
        _default_area_keys = json.load(f)["areaKeys"]
else:
    logger.warning("Default area keys file not found, using empty filter")
    _default_area_keys = {}


def get_message(*args):
    return " ".join(args)


def warning(*args):
    logger.warning(" ".join(args))


def error(*args):
    logger.error(" ".join(args))


def json2geojson(
    data,
    filter_used_refs=True,
    log_level="ERROR",
    area_keys: Optional[dict] = None,
    polygon_features: Optional[list] = None,
    raise_on_failure=False,
):
    if isinstance(data, str):
        data = json.loads(data)
    return _json2geojson(
        data, filter_used_refs, log_level, area_keys, polygon_features, raise_on_failure
    )


def xml2geojson(
    xml_str,
    filter_used_refs=True,
    log_level="ERROR",
    area_keys: Optional[dict] = None,
    polygon_features: Optional[list] = None,
    raise_on_failure=False,
):
    data = parse_xml(xml_str)
    return _json2geojson(
        data, filter_used_refs, log_level, area_keys, polygon_features, raise_on_failure
    )


def json2shapes(
    data,
    filter_used_refs=True,
    log_level="ERROR",
    area_keys: Optional[dict] = None,
    polygon_features: Optional[list] = None,
    raise_on_failure=False,
):
    if isinstance(data, str):
        data = json.loads(data)
    return _json2shapes(
        data, filter_used_refs, log_level, area_keys, polygon_features, raise_on_failure
    )


def xml2shapes(
    xml_str,
    filter_used_refs=True,
    log_level="ERROR",
    area_keys: Optional[dict] = None,
    polygon_features: Optional[list] = None,
    raise_on_failure=False,
):
    data = parse_xml(xml_str)
    return _json2shapes(
        data, filter_used_refs, log_level, area_keys, polygon_features, raise_on_failure
    )


def _json2geojson(
    data,
    filter_used_refs=True,
    log_level="ERROR",
    area_keys: Optional[dict] = None,
    polygon_features: Optional[list] = None,
    raise_on_failure=False,
):
    features = []
    for shape in _json2shapes(
        data, filter_used_refs, log_level, area_keys, polygon_features, raise_on_failure
    ):
        feature = shape_to_feature(shape["shape"], shape["properties"])
        features.append(feature)

    return {"type": "FeatureCollection", "features": features}


def _json2shapes(
    data,
    filter_used_refs=True,
    log_level="ERROR",
    area_keys: Optional[dict] = None,
    polygon_features: Optional[list] = None,
    raise_on_failure=False,
):
    logger.setLevel(log_level)
    shapes = []

    refs = [el for el in data["elements"] if el["type"] in ["node", "way", "relation"]]

    refs_index = build_refs_index(refs)

    for el in data["elements"]:
        shape = element_to_shape(
            el, refs_index, area_keys, polygon_features, raise_on_failure=raise_on_failure
        )
        if shape is not None:
            shapes.append(shape)
        else:
            el_type = el.get("type", "unknown")
            el_id = el.get("id", "unknown")
            # Provide more helpful message for relations with missing members
            if el_type == "relation" and "members" in el:
                warning(
                    f"Element not converted: {el_type} {el_id} (incomplete relation - some member ways/nodes are missing or have no geometry)"
                )
            else:
                warning("Element not converted", pformat(el_id))

    if not filter_used_refs:
        return shapes

    used = {ref["id"]: ref["used"] for ref in refs if "used" in ref}
    filtered_shapes = []
    for shape in shapes:
        if "properties" not in shape:
            warning("Shape without props", pformat(shape))
        if shape["properties"]["id"] in used:
            continue
        filtered_shapes.append(shape)

    return filtered_shapes


def element_to_shape(
    el,
    refs_index=None,
    area_keys: Optional[dict] = None,
    polygon_features: Optional[list] = None,
    raise_on_failure=False,
):
    t = el["type"]
    if t == "node":
        return node_to_shape(el)
    if t == "way":
        return way_to_shape(
            el, refs_index, area_keys, polygon_features, raise_on_failure=raise_on_failure
        )
    if t == "relation":
        return relation_to_shape(el, refs_index, raise_on_failure=raise_on_failure)
    warning("Failed to convert element to shape")
    return None


def _get_ref_name(el_type, id):
    return "%s/%s" % (el_type, id)


def get_ref_name(el):
    return _get_ref_name(el["type"], el["id"])


def _get_ref(el_type, id, refs_index, silent=False):
    key = _get_ref_name(el_type, id)
    if key in refs_index:
        return refs_index[key]
    if not silent:
        logger.debug("Element not found in refs_index: %s %s", el_type, id)
    return None


def get_ref(ref_el, refs_index, silent=False):
    return _get_ref(ref_el["type"], ref_el["ref"], refs_index, silent)


def get_node_ref(id, refs_index, silent=False):
    return _get_ref("node", id, refs_index, silent)


def build_refs_index(elements):
    return {get_ref_name(el): el for el in elements}


# Tag keys that don't make an element a feature in its own right
# (same blacklist as osmtogeojson)
UNINTERESTING_TAGS = {
    "source",
    "source_ref",
    "source:ref",
    "history",
    "attribution",
    "created_by",
    "tiger:county",
    "tiger:tlid",
    "tiger:upload_uuid",
}


def has_interesting_tags(tags, ignore_tags=None):
    ignore_tags = ignore_tags or {}
    for key, value in (tags or {}).items():
        if key in UNINTERESTING_TAGS:
            continue
        if key in ignore_tags and ignore_tags[key] == value:
            continue
        return True
    return False


def node_to_shape(node):
    return {"shape": Point(node["lon"], node["lat"]), "properties": get_element_props(node)}


def get_element_props(el, keys: list = None):
    keys = keys or ["type", "id", "tags", "nodes", "timestamp", "user", "uid", "version"]
    return {key: el[key] for key in keys if key in el}


def convert_coords_to_lists(coords):
    if len(coords) < 1:
        return []

    if isinstance(coords[0], float):
        return list(coords)

    return [convert_coords_to_lists(c) for c in coords]


def shape_to_feature(g, props: dict = None):
    props = props or {}
    # shapely returns tuples (we need lists)
    g = mapping(g)
    g["coordinates"] = convert_coords_to_lists(g["coordinates"])
    return {"type": "Feature", "properties": props, "geometry": g}


def orient_multipolygon(p):
    p = [orient(geom) for geom in p.geoms]
    return MultiPolygon(p)


def fix_invalid_polygon(p):
    if not p.is_valid:
        logger.info("Invalid geometry! Try to fix with 0 buffer")
        p = p.buffer(0)
        if p.is_valid:
            logger.info("Geometry fixed!")
    return p


def way_to_shape(
    way,
    refs_index: dict = None,
    area_keys: Optional[dict] = None,
    polygon_features: Optional[list] = None,
    raise_on_failure=False,
):
    refs_index = refs_index or {}
    if "center" in way:
        center = way["center"]
        return {"shape": Point(center["lon"], center["lat"]), "properties": get_element_props(way)}

    if "geometry" in way and len(way["geometry"]) > 0:
        coords = [[nd["lon"], nd["lat"]] for nd in way["geometry"]]

    elif "nodes" in way and len(way["nodes"]) > 0:
        coords = []
        for ref in way["nodes"]:
            node = get_node_ref(ref, refs_index)
            if node:
                node["used"] = way["id"]
                coords.append([node["lon"], node["lat"]])
            else:
                message = get_message(
                    "Node not found in index", pformat(ref), "for way", pformat(way)
                )
                warning(message)
                if raise_on_failure:
                    raise Exception(message)
                return None

    elif "ref" in way:
        # Try to get ref silently first (common in incomplete relation data)
        ref = get_ref(way, refs_index, silent=True)
        if not ref:
            # Only log debug message, not a warning, as this is expected with incomplete data
            logger.debug(
                "Ref for way not found in index: %s (ref: %s)", way.get("type"), way.get("ref")
            )
            if raise_on_failure:
                message = get_message("Ref for way not found in index", pformat(way))
                raise Exception(message)
            return None

        if "id" in way:
            ref["used"] = way["id"]
        elif "used" in way:
            ref["used"] = way["used"]
        else:
            # filter will not work for this situation
            warning("Failed to mark ref as used", pformat(ref), "for way", pformat(way))
            # do we need to raise expection here? I don't think so
        ref_way = way_to_shape(
            ref, refs_index, area_keys, polygon_features, raise_on_failure=raise_on_failure
        )
        if ref_way is None:
            message = get_message("Way by ref not converted to shape", pformat(way))
            warning(message)
            if raise_on_failure:
                raise Exception(message)
            return None
        coords = (
            ref_way["shape"].exterior if isinstance(ref_way["shape"], Polygon) else ref_way["shape"]
        ).coords

    else:
        # throw exception
        message = get_message("Relation has way without nodes", pformat(way))
        warning(message)
        if raise_on_failure:
            raise Exception(message)
        return None

    if len(coords) < 2:
        message = get_message("Not found coords for way", pformat(way))
        warning(message)
        if raise_on_failure:
            raise Exception(message)
        return None

    props = get_element_props(way)
    if is_geometry_polygon(way, area_keys, polygon_features):
        try:
            poly = fix_invalid_polygon(Polygon(coords))
            return {"shape": poly, "properties": props}
        except Exception:
            message = get_message("Failed to generate polygon from way", pformat(way))
            warning(message)
            if raise_on_failure:
                raise Exception(message)
            return None
    else:
        return {"shape": LineString(coords), "properties": props}


def is_exception(node, area_keys: Optional[dict] = None):
    area_keys = area_keys or _default_area_keys
    for tag in node["tags"]:
        if tag in area_keys:
            value = node["tags"][tag]
            return value in area_keys[tag] and area_keys[tag][value]
    return False


def is_same_coords(a, b):
    return a["lat"] == b["lat"] and a["lon"] == b["lon"]


def is_geometry_polygon(
    node, area_keys: Optional[dict] = None, polygon_features: Optional[list] = None
):
    if "tags" not in node:
        return False
    tags = node["tags"]

    if "area" in tags and tags["area"] == "no":
        return False

    if "area" in tags and tags["area"] == "yes":
        return True

    if "type" in tags and tags["type"] == "multipolygon":
        return True

    # Fix for issue #7, but should be handled by id-area-keys or osm-polygon-features
    # For example https://github.com/tyrasd/osm-polygon-features/issues/5
    if "geometry" in node and not is_same_coords(node["geometry"][0], node["geometry"][-1]):
        return False

    # For issue #7 and situation with barrier=wall
    if "nodes" in node and node["nodes"][0] != node["nodes"][-1]:
        return False

    is_polygon = is_geometry_polygon_without_exceptions(node, polygon_features)
    if is_polygon:
        return not is_exception(node, area_keys)
    return False


def is_geometry_polygon_without_exceptions(node, polygon_features: Optional[list] = None):
    """
    Determine if a node should be treated as a polygon based on its tags.

    Logic precedence:
    1. Blacklists take first precedence: any tag/value on a blacklist -> NOT a polygon
    2. Whitelists take second precedence: any tag/value on a whitelist -> IS a polygon
    3. "all" rules: any tag with polygon="all" -> IS a polygon
    4. Default: if no rules match -> NOT a polygon
    """
    polygon_features = polygon_features or _default_polygon_features
    tags = node["tags"]

    # First pass: check blacklists (highest precedence)
    for rule in polygon_features:
        if rule["key"] in tags and rule["polygon"] == "blacklist":
            if tags[rule["key"]] in rule["values"]:
                return False

    # Second pass: check whitelists and "all" rules
    for rule in polygon_features:
        if rule["key"] in tags:
            if rule["polygon"] == "blacklist":
                blacklist_whitelisted = False
                for rule2 in polygon_features:
                    if rule["key"] == rule2["key"] and rule2["polygon"] == "whitelist":
                        blacklist_whitelisted = True
                if not blacklist_whitelisted:
                    return True
            if rule["polygon"] == "all":
                return True
            if rule["polygon"] == "whitelist" and tags[rule["key"]] in rule["values"]:
                return True

    # Default: not a polygon
    return False


def log_missing_members_info(rel_id, missing_members, total_members, converted_count):
    """Log informative message about missing relation members.

    Args:
        rel_id: The relation ID
        missing_members: List of missing member dictionaries
        total_members: Total number of members in the relation
        converted_count: Number of successfully converted members
    """
    if missing_members and converted_count > 0:
        missing_info = ", ".join(
            [f"{m.get('role', 'no-role')}:{m['ref']}" for m in missing_members[:5]]
        )
        if len(missing_members) > 5:
            missing_info += f" (and {len(missing_members) - 5} more)"
        logger.info(
            "Relation %s: converted with %d/%d members (missing: %s)",
            rel_id,
            converted_count,
            total_members,
            missing_info,
        )


def relation_to_shape(
    rel,
    refs_index,
    area_keys: Optional[dict] = None,
    polygon_features: Optional[list] = None,
    raise_on_failure=False,
):
    if "center" in rel:
        center = rel["center"]
        return {"shape": Point(center["lon"], center["lat"]), "properties": get_element_props(rel)}

    try:
        if is_geometry_polygon(rel, area_keys, polygon_features):
            return multipolygon_relation_to_shape(
                rel, refs_index, raise_on_failure=raise_on_failure
            )
        return multiline_realation_to_shape(rel, refs_index, raise_on_failure=raise_on_failure)
    except Exception as e:
        message = get_message("Failed to convert relation to shape: \n", pformat(e), pformat(rel))
        error(message)
        if raise_on_failure:
            raise Exception(message)


def multiline_realation_to_shape(
    rel,
    refs_index,
    area_keys: Optional[dict] = None,
    polygon_features: Optional[list] = None,
    raise_on_failure=False,
):
    lines = []
    missing_members = []
    unhandled_members = []

    if "members" in rel:
        members = rel["members"]
    else:
        found_ref = get_ref(rel, refs_index)
        if not found_ref:
            message = get_message("Ref for multiline relation not found in index", pformat(rel))
            error(message)
            if raise_on_failure:
                raise Exception(message)
            return None
        members = found_ref["members"]

    for member in members:
        if member["type"] == "way":
            way_shape = way_to_shape(
                member, refs_index, area_keys, polygon_features, raise_on_failure=raise_on_failure
            )
        elif member["type"] == "relation":
            found_member = get_ref(member, refs_index, silent=True)
            if found_member:
                found_member["used"] = rel["id"]
            way_shape = element_to_shape(
                member, refs_index, area_keys, polygon_features, raise_on_failure=raise_on_failure
            )
        else:
            unhandled_members.append(member)
            logger.debug(
                "Multiline member type not handled: %s (role: %s)",
                member["type"],
                member.get("role", ""),
            )
            if raise_on_failure:
                message = get_message("multiline member not handled", pformat(member))
                raise Exception(message)
            continue

        if way_shape is None:
            missing_members.append(member)
            if raise_on_failure:
                message = get_message("Failed to make way in relation", pformat(rel))
                raise Exception(message)
            continue

        if isinstance(way_shape["shape"], Polygon):
            # this should not happen on real data
            way_shape["shape"] = LineString(way_shape["shape"].exterior.coords)
        lines.append(way_shape["shape"])

    # Log info about missing members if any
    log_missing_members_info(rel.get("id", "unknown"), missing_members, len(members), len(lines))

    if len(lines) < 1:
        message = get_message("No lines for multiline relation", pformat(rel))
        warning(message)
        if raise_on_failure:
            raise Exception(message)
        return None

    multiline = MultiLineString(lines)
    multiline = linemerge(multiline)
    return {"shape": multiline, "properties": get_element_props(rel)}


def multipolygon_relation_to_shape(
    rel,
    refs_index,
    area_keys: Optional[dict] = None,
    polygon_features: Optional[list] = None,
    raise_on_failure=False,
):
    # List of Tuple (role, multipolygon)
    shapes = []
    missing_members = []
    non_way_members = []

    if "members" in rel:
        members = rel["members"]
    else:
        found_ref = get_ref(rel, refs_index)
        if not found_ref:
            message = get_message("Ref for multipolygon relation not found in index", pformat(rel))
            error(message)
            if raise_on_failure:
                raise Exception(message)
            return None
        members = found_ref["members"]

    for member in members:
        if member["type"] != "way":
            non_way_members.append(member)
            logger.debug(
                "Multipolygon member type not handled: %s (role: %s)",
                member["type"],
                member.get("role", ""),
            )
            if raise_on_failure:
                message = get_message("Multipolygon member not handled", pformat(member))
                raise Exception(message)
            continue

        member["used"] = rel["id"]

        # When member ways are also returned as separate elements (e.g. "rel(ID); way(r);
        # out geom;"), members carry inline geometry and way_to_shape never touches the
        # indexed element, so mark it as used here. Ways with their own interesting tags
        # (islands inside a lake, nature reserves, ...) are features in their own right
        # and stay in the output; for outer ways the relation's tags don't count as
        # interesting (old-style multipolygon tagging).
        found_way = get_ref(member, refs_index, silent=True)
        if found_way is not None:
            ignore_tags = rel.get("tags") if member.get("role") == "outer" else None
            if not has_interesting_tags(found_way.get("tags"), ignore_tags):
                found_way["used"] = rel["id"]

        way_shape = way_to_shape(
            member, refs_index, area_keys, polygon_features, raise_on_failure=raise_on_failure
        )
        if way_shape is None:
            missing_members.append(member)
            if raise_on_failure:
                message = get_message(
                    "Failed to make way", pformat(member), "in relation", pformat(rel)
                )
                raise Exception(message)
            continue

        if isinstance(way_shape["shape"], Polygon):
            way_shape["shape"] = LineString(way_shape["shape"].exterior.coords)

        shapes.append((member["role"], way_shape["shape"], member["ref"]))

    # Log info about missing members if any
    log_missing_members_info(rel.get("id", "unknown"), missing_members, len(members), len(shapes))

    multipolygon = _convert_shapes_to_multipolygon(shapes, raise_on_failure=raise_on_failure)
    if multipolygon is None:
        message = get_message(
            "Failed to convert computed shapes to multipolygon", pformat(rel["id"])
        )
        warning(message)
        if raise_on_failure:
            raise Exception(message)
        return None

    multipolygon = fix_invalid_polygon(multipolygon)
    multipolygon = to_multipolygon(multipolygon, raise_on_failure=raise_on_failure)
    multipolygon = orient_multipolygon(multipolygon)  # do we need this?

    if multipolygon is None:
        message = get_message(
            "Failed to fix multipolygon. Report this in github please!", pformat(rel)
        )
        warning(message)
        if raise_on_failure:
            raise Exception(message)
        return None

    return {"shape": multipolygon, "properties": get_element_props(rel)}


def to_multipolygon(obj, raise_on_failure=False):
    if isinstance(obj, MultiPolygon):
        return obj

    if isinstance(obj, GeometryCollection):
        p = [el for el in obj if isinstance(el, Polygon)]
        return MultiPolygon(p)

    if isinstance(obj, Polygon):
        return MultiPolygon([obj])

    # throw exception
    message = get_message("Failed to convert to multipolygon", type(obj))
    warning(message)
    if raise_on_failure:
        raise Exception(message)
    return None


def _convert_lines_to_multipolygon(lines, raise_on_failure=False):
    multi_line = MultiLineString(lines)
    merged_line = linemerge(multi_line)
    if isinstance(merged_line, MultiLineString):
        polygons = []
        for line in merged_line.geoms:
            try:
                poly = Polygon(line)
                if poly.is_valid:
                    polygons.append(poly)
                else:
                    polygons.append(poly.buffer(0))
            except Exception:
                # throw exception
                message = get_message("Failed to build polygon", pformat(line))
                warning(message)
                if raise_on_failure:
                    raise Exception(message)
        return to_multipolygon(unary_union(polygons), raise_on_failure=raise_on_failure)
    try:
        poly = Polygon(merged_line)
    except Exception as e:
        message = get_message("Failed to convert lines to polygon", pformat(e))
        warning(message)
        if raise_on_failure:
            raise Exception(message)
        # traceback.print_exc()
        return None
    return to_multipolygon(poly, raise_on_failure=raise_on_failure)


def _convert_shapes_to_multipolygon(shapes, raise_on_failure=False):
    if len(shapes) < 1:
        message = "Failed to create multipolygon (Empty)"
        warning(message)
        if raise_on_failure:
            raise Exception(message)
        return None

    # Group shapes by role using consecutive grouping
    # This preserves structure for complex cases (e.g., Baarle-Nassau with outer-inner-outer)
    import itertools

    groups = []
    for role, group in itertools.groupby(shapes, lambda s: s[0]):
        lines_and_ids = [(_[1], _[2]) for _ in group]
        geom = _convert_lines_to_multipolygon(
            [_[0] for _ in lines_and_ids], raise_on_failure=raise_on_failure
        )
        groups.append((role, geom, [_[1] for _ in lines_and_ids]))

    # Fix issue #54: If we have multiple outer groups, try merging them
    # Only merge if the result is a single polygon (they actually connect)
    outer_indices = [i for i, (role, _, _) in enumerate(groups) if role == "outer"]
    if len(outer_indices) > 1:
        # Try merging all outer lines together
        all_outer_lines = [line for role, line, _ in shapes if role == "outer"]
        all_outer_ids = [ref_id for role, _, ref_id in shapes if role == "outer"]
        merged = _convert_lines_to_multipolygon(all_outer_lines, raise_on_failure=raise_on_failure)

        # Count polygons: only merge if result is exactly 1 polygon
        merged_count = len(list(merged.geoms)) if isinstance(merged, MultiPolygon) else 1
        if merged_count == 1:
            # Single polygon - replace all outer groups with merged one
            for i in reversed(outer_indices):
                groups.pop(i)
            groups.insert(outer_indices[0], ("outer", merged, all_outer_ids))

    # Find the outer geometry to use as base
    multipolygon = None
    base_index = -1
    for i, (role, geom, ids) in enumerate(groups):
        if role == "outer":
            multipolygon = geom
            base_index = i
            break

    if base_index < 0:
        message = 'Failed to create multipolygon. Shape with "outer" role not found'
        warning(message)
        if raise_on_failure:
            raise Exception(message)
        return None

    if not multipolygon.is_valid:
        group_ids = groups[base_index][2]
        message = get_message(
            'Failed to create multipolygon. Base shape with role "outer" is invalid. Group ids:',
            pformat(group_ids),
        )
        warning(message)
        if raise_on_failure:
            raise Exception(message)
        return None

    # Iterate over the rest if there are any
    for i, (role, geom, ids) in enumerate(groups):
        if i == base_index:
            continue

        if role == "inner":
            multipolygon = multipolygon.difference(geom)
        else:
            multipolygon = multipolygon.union(geom)

        if multipolygon is None:
            message = get_message("Failed to compute multipolygon. Failing geometry:", role, geom)
            warning(message)
            if raise_on_failure:
                raise Exception(message)
            return None

    return multipolygon
