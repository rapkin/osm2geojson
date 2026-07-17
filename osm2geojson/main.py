"""Main module for converting OSM data to GeoJSON format.

This module provides the core functionality for converting OpenStreetMap (OSM)
and Overpass API data into GeoJSON format, handling various geometry types
including nodes, ways, and relations.
"""

import json
import logging
import os
from pprint import pformat
from typing import Optional, Union

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


class ConversionError(Exception):
    """Raised when OSM data cannot be converted (with raise_on_failure=True)."""


def get_message(*args):
    return " ".join(args)


def warning(*args):
    logger.warning(" ".join(args))


def error(*args):
    logger.error(" ".join(args))


def _copy_elements(elements):
    # The conversion annotates elements (and relation members) with bookkeeping
    # keys ("used", "_relation_member"); copy enough structure that the caller's
    # data stays untouched. Only these dicts gain keys - nested values (tags,
    # geometry) are never mutated, so a shallow copy per dict is sufficient.
    copied = []
    for el in elements:
        el = dict(el)
        if "members" in el:
            el["members"] = [dict(member) for member in el["members"]]
        copied.append(el)
    return copied


def json2geojson(
    data: Union[str, dict],
    *,
    filter_used_refs: bool = True,
    log_level: Optional[str] = None,
    area_keys: Optional[dict] = None,
    polygon_features: Optional[list] = None,
    raise_on_failure: bool = False,
) -> dict:
    if isinstance(data, str):
        data = json.loads(data)
    else:
        data = {**data, "elements": _copy_elements(data["elements"])}
    return _json2geojson(
        data, filter_used_refs, log_level, area_keys, polygon_features, raise_on_failure
    )


def xml2geojson(
    xml_str: str,
    *,
    filter_used_refs: bool = True,
    log_level: Optional[str] = None,
    area_keys: Optional[dict] = None,
    polygon_features: Optional[list] = None,
    raise_on_failure: bool = False,
) -> dict:
    data = parse_xml(xml_str)
    return _json2geojson(
        data, filter_used_refs, log_level, area_keys, polygon_features, raise_on_failure
    )


def json2shapes(
    data: Union[str, dict],
    *,
    filter_used_refs: bool = True,
    log_level: Optional[str] = None,
    area_keys: Optional[dict] = None,
    polygon_features: Optional[list] = None,
    raise_on_failure: bool = False,
) -> list:
    if isinstance(data, str):
        data = json.loads(data)
    else:
        data = {**data, "elements": _copy_elements(data["elements"])}
    return _json2shapes(
        data, filter_used_refs, log_level, area_keys, polygon_features, raise_on_failure
    )


def xml2shapes(
    xml_str: str,
    *,
    filter_used_refs: bool = True,
    log_level: Optional[str] = None,
    area_keys: Optional[dict] = None,
    polygon_features: Optional[list] = None,
    raise_on_failure: bool = False,
) -> list:
    data = parse_xml(xml_str)
    return _json2shapes(
        data, filter_used_refs, log_level, area_keys, polygon_features, raise_on_failure
    )


def _json2geojson(
    data,
    filter_used_refs=True,
    log_level=None,
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
    log_level=None,
    area_keys: Optional[dict] = None,
    polygon_features: Optional[list] = None,
    raise_on_failure=False,
):
    if log_level is not None:
        logger.setLevel(log_level)
    shapes = []

    elements = deduplicate_elements(data["elements"])

    refs = [el for el in elements if el["type"] in ["node", "way", "relation"]]

    refs_index = build_refs_index(refs)

    for node in mark_relation_members(refs, refs_index):
        elements.append(node)
        refs.append(node)
        refs_index[get_ref_name(node)] = node

    for el in elements:
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

    if filter_used_refs:
        # key by (type, id): node, way and relation ids live in separate id-spaces
        used = {(ref["type"], ref["id"]): ref["used"] for ref in refs if "used" in ref}
        filtered_shapes = []
        for shape in shapes:
            if "properties" not in shape:
                warning("Shape without props", pformat(shape))
            if (
                not shape.get("keep")
                and (
                    shape["properties"].get("type"),
                    shape["properties"].get("id"),
                )
                in used
            ):
                continue
            filtered_shapes.append(shape)
        shapes = filtered_shapes

    for shape in shapes:
        shape.pop("keep", None)  # internal filtering flag, not part of the result
    return shapes


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


def mark_relation_members(elements, refs_index):
    """Flag elements that are direct members of a relation.

    Such elements are features in their own right (e.g. an admin_centre node)
    even when they also serve as way vertices. Node members that only exist
    inline ("out geom" responses) are synthesized into standalone elements so
    they show up as Point features: they are returned for the caller to add
    to the element list and index.
    """
    synthesized = {}
    for el in elements:
        if el["type"] != "relation":
            continue
        for member in el.get("members", []):
            found = get_ref(member, refs_index, silent=True)
            if found is None:
                # a node already synthesized for another relation's member
                found = synthesized.get(_get_ref_name(member["type"], member["ref"]))
            if found is not None:
                found["_relation_member"] = True
            elif member["type"] == "node" and "lat" in member and "lon" in member:
                node = {
                    "type": "node",
                    "id": member["ref"],
                    "lat": member["lat"],
                    "lon": member["lon"],
                    "_relation_member": True,
                }
                if member.get("tags"):
                    node["tags"] = member["tags"]
                synthesized[get_ref_name(node)] = node
    return list(synthesized.values())


def _element_rank(el):
    # newer version first, then completeness (a skeleton has fewer keys)
    return (el.get("version", 0), len(el))


def deduplicate_elements(elements):
    """Drop repeated elements, keeping the newest / most complete version.

    Overpass unions (e.g. "way(...); >;") can return the same element twice,
    sometimes as a skeleton. Tags of same-version duplicates (overlapping
    queries) are merged.
    """
    best = {}
    order = []
    for el in elements:
        if "type" not in el or "id" not in el:
            key = ("__no_id__", len(order))
        else:
            key = (el["type"], el["id"])
        seen = best.get(key)
        if seen is None:
            order.append(key)
            best[key] = el
            continue
        winner, loser = (el, seen) if _element_rank(el) > _element_rank(seen) else (seen, el)
        # the loser fills in fields the winner lacks: Overpass unions can split
        # one element over several copies (e.g. "out tags;" + "out skel geom;"),
        # and dropping the geometry-bearing copy would lose the element entirely
        merged = {**loser, **winner}
        if winner.get("version") == loser.get("version"):
            merged_tags = {**(loser.get("tags") or {}), **(winner.get("tags") or {})}
            if merged_tags:
                merged["tags"] = merged_tags
        best[key] = merged
    return [best[key] for key in order]


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
        if key in ignore_tags and (ignore_tags[key] is True or ignore_tags[key] == value):
            continue
        return True
    return False


def node_to_shape(node):
    if "lon" not in node or "lat" not in node:
        logger.debug("Node without coordinates: %s", node.get("id"))
        return None
    return {"shape": Point(node["lon"], node["lat"]), "properties": get_element_props(node)}


def bounds_to_shape(bounds):
    return Polygon(
        [
            [bounds["minlon"], bounds["minlat"]],
            [bounds["maxlon"], bounds["minlat"]],
            [bounds["maxlon"], bounds["maxlat"]],
            [bounds["minlon"], bounds["maxlat"]],
            [bounds["minlon"], bounds["minlat"]],
        ]
    )


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

    if way.get("geometry"):
        # tolerate null/empty vertices (tainted "out geom" data) — build partial geometry
        coords = [
            [nd["lon"], nd["lat"]]
            for nd in way["geometry"]
            if nd is not None and "lon" in nd and "lat" in nd
        ]

    elif "nodes" in way and len(way["nodes"]) > 0:
        coords = []
        for ref in way["nodes"]:
            node = get_node_ref(ref, refs_index)
            if node is not None and "lon" not in node:
                # skeleton node (e.g. "out ids") - no geometry to contribute
                node = None
            if node:
                # nodes with own interesting tags (POIs) or referenced by relations
                # stay separate features
                if not (has_interesting_tags(node.get("tags")) or node.get("_relation_member")):
                    node["used"] = way["id"]
                coords.append([node["lon"], node["lat"]])
            else:
                message = get_message(
                    "Node not found in index", pformat(ref), "for way", pformat(way)
                )
                warning(message)
                if raise_on_failure:
                    raise ConversionError(message)
                # build partial geometry from the nodes we do have

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
                raise ConversionError(message)
            return None

        used_by = way.get("id", way.get("used"))
        if used_by is not None and not has_interesting_tags(ref.get("tags")):
            ref["used"] = used_by
        ref_way = way_to_shape(
            ref, refs_index, area_keys, polygon_features, raise_on_failure=raise_on_failure
        )
        if ref_way is None:
            message = get_message("Way by ref not converted to shape", pformat(way))
            warning(message)
            if raise_on_failure:
                raise ConversionError(message)
            return None
        coords = (
            ref_way["shape"].exterior if isinstance(ref_way["shape"], Polygon) else ref_way["shape"]
        ).coords

    elif "bounds" in way:
        # "out bb" responses carry only a bounding box
        return {"shape": bounds_to_shape(way["bounds"]), "properties": get_element_props(way)}

    else:
        # throw exception
        message = get_message("Relation has way without nodes", pformat(way))
        warning(message)
        if raise_on_failure:
            raise ConversionError(message)
        return None

    if len(coords) < 2:
        if "bounds" in way:
            return {"shape": bounds_to_shape(way["bounds"]), "properties": get_element_props(way)}
        message = get_message("Not found coords for way", pformat(way))
        warning(message)
        if raise_on_failure:
            raise ConversionError(message)
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
                raise ConversionError(message)
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
    if a is None or b is None:
        return False
    return a["lat"] == b["lat"] and a["lon"] == b["lon"]


def is_geometry_polygon(
    node, area_keys: Optional[dict] = None, polygon_features: Optional[list] = None
):
    if "tags" not in node:
        return False
    tags = node["tags"]

    if "area" in tags and tags["area"] == "no":
        return False

    # An unclosed way is never a polygon, whatever its tags say
    # (also covers issue #7 and barrier=wall)
    if "geometry" in node and not is_same_coords(node["geometry"][0], node["geometry"][-1]):
        return False
    if "nodes" in node and node["nodes"][0] != node["nodes"][-1]:
        return False

    if "area" in tags and tags["area"] == "yes":
        return True

    if "type" in tags and tags["type"] in ("multipolygon", "boundary"):
        return True

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

    shape = None
    try:
        if is_geometry_polygon(rel, area_keys, polygon_features):
            shape = multipolygon_relation_to_shape(
                rel, refs_index, raise_on_failure=raise_on_failure
            )
        else:
            shape = multiline_realation_to_shape(rel, refs_index, raise_on_failure=raise_on_failure)
    except Exception as e:
        message = get_message("Failed to convert relation to shape: \n", pformat(e), pformat(rel))
        error(message)
        if raise_on_failure:
            raise ConversionError(message)

    if shape is None and "bounds" in rel:
        # "out bb" responses carry only a bounding box
        return {"shape": bounds_to_shape(rel["bounds"]), "properties": get_element_props(rel)}
    return shape


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
                raise ConversionError(message)
            return None
        members = found_ref["members"]

    rel_id = rel.get("id", rel.get("ref"))
    rel_type = (rel.get("tags") or {}).get("type")

    for member in members:
        if member["type"] == "way":
            # for linear relation types, members without own interesting tags are
            # represented by the relation itself (same rule as osmtogeojson)
            if rel_type in ("route", "waterway"):
                found_way = get_ref(member, refs_index, silent=True)
                if found_way is not None and not has_interesting_tags(found_way.get("tags")):
                    found_way["used"] = rel_id
            way_shape = way_to_shape(
                member, refs_index, area_keys, polygon_features, raise_on_failure=raise_on_failure
            )
        elif member["type"] == "relation":
            found_member = get_ref(member, refs_index, silent=True)
            if found_member is not None and not has_interesting_tags(found_member.get("tags")):
                found_member["used"] = rel_id
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
                raise ConversionError(message)
            continue

        if way_shape is None:
            missing_members.append(member)
            if raise_on_failure:
                message = get_message("Failed to make way in relation", pformat(rel))
                raise ConversionError(message)
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
            raise ConversionError(message)
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
                raise ConversionError(message)
            return None
        members = found_ref["members"]

    rel_id = rel.get("id", rel.get("ref"))

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
                raise ConversionError(message)
            continue

        member["used"] = rel_id
        mark_member_way_used(member, rel, refs_index, rel_id)

        way_shape = way_to_shape(
            member, refs_index, area_keys, polygon_features, raise_on_failure=raise_on_failure
        )
        if way_shape is None:
            missing_members.append(member)
            if raise_on_failure:
                message = get_message(
                    "Failed to make way", pformat(member), "in relation", pformat(rel)
                )
                raise ConversionError(message)
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
            raise ConversionError(message)
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
            raise ConversionError(message)
        return None

    old_style = old_style_multipolygon_shape(rel, members, refs_index, rel_id, multipolygon)
    if old_style is not None:
        return old_style
    return {"shape": multipolygon, "properties": get_element_props(rel)}


def mark_member_way_used(member, rel, refs_index, rel_id):
    """Mark the indexed element behind a relation-member way as used.

    When member ways are also returned as separate elements (e.g. "rel(ID);
    way(r); out geom;"), members carry inline geometry and way_to_shape never
    touches the indexed element, so it must be marked here. Ways with their
    own interesting tags (islands inside a lake, nature reserves, ...) are
    features in their own right and stay in the output. For ref-resolved
    outer ways the relation's tags don't count as interesting (old-style
    multipolygon tagging, same rule as osmtogeojson); members with inline
    geometry keep their own tags meaningful.
    """
    found_way = get_ref(member, refs_index, silent=True)
    if found_way is None:
        return
    ignore_tags = None
    if member.get("role") == "outer" and "geometry" not in member:
        ignore_tags = rel.get("tags")
    if not has_interesting_tags(found_way.get("tags"), ignore_tags):
        found_way["used"] = rel_id


def old_style_multipolygon_shape(rel, members, refs_index, rel_id, multipolygon):
    """Attribute an old-style multipolygon to its outer way, like osmtogeojson.

    Old-style tagging puts the tags on the single outer way while the relation
    carries only type=multipolygon. Returns the shape dict for such relations,
    or None for modern multipolygons (tags on the relation).
    """
    outer_members = [m for m in members if m.get("role", "outer") in ("outer", "")]
    if len(outer_members) != 1 or has_interesting_tags(rel.get("tags"), {"type": True}):
        return None
    outer = outer_members[0]
    found_way = get_ref(outer, refs_index, silent=True)
    if found_way is not None:
        found_way["used"] = rel_id  # the way is represented by this feature now
        props = get_element_props(found_way)
    else:
        # "out geom" data: the member way is not a separate element
        props = {"type": "way", "id": outer["ref"]}
        if outer.get("tags"):
            props["tags"] = outer["tags"]
    # this feature carries the way's id on purpose - "keep" shields it from filter_used_refs
    return {"shape": multipolygon, "properties": props, "keep": True}


def to_multipolygon(obj, raise_on_failure=False):
    if isinstance(obj, MultiPolygon):
        return obj

    if isinstance(obj, GeometryCollection):
        p = [el for el in obj.geoms if isinstance(el, Polygon)]
        return MultiPolygon(p)

    if isinstance(obj, Polygon):
        return MultiPolygon([obj])

    # throw exception
    message = get_message("Failed to convert to multipolygon", type(obj))
    warning(message)
    if raise_on_failure:
        raise ConversionError(message)
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
                    raise ConversionError(message)
        return to_multipolygon(unary_union(polygons), raise_on_failure=raise_on_failure)
    try:
        poly = Polygon(merged_line)
    except Exception as e:
        message = get_message("Failed to convert lines to polygon", pformat(e))
        warning(message)
        if raise_on_failure:
            raise ConversionError(message)
        # traceback.print_exc()
        return None
    return to_multipolygon(poly, raise_on_failure=raise_on_failure)


def _convert_shapes_to_multipolygon(shapes, raise_on_failure=False):
    if len(shapes) < 1:
        message = "Failed to create multipolygon (Empty)"
        warning(message)
        if raise_on_failure:
            raise ConversionError(message)
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
            raise ConversionError(message)
        return None

    if not multipolygon.is_valid:
        group_ids = groups[base_index][2]
        message = get_message(
            'Failed to create multipolygon. Base shape with role "outer" is invalid. Group ids:',
            pformat(group_ids),
        )
        warning(message)
        if raise_on_failure:
            raise ConversionError(message)
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
                raise ConversionError(message)
            return None

    return multipolygon
