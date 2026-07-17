#!/usr/bin/env python3

import argparse
import json
import os
import sys
from contextlib import nullcontext

from .main import json2geojson, xml2geojson


def setup_parser() -> argparse.ArgumentParser:
    def file(v: str) -> str:
        if not os.path.exists(v):
            raise argparse.ArgumentTypeError(f"file not found: {v}")
        return v

    parser = argparse.ArgumentParser(prog=__package__)
    parser.add_argument("infile", type=file, help="OSM or Overpass JSON file to convert to GeoJSON")
    parser.add_argument(
        "outfile", help="write output of the processing to the specified file (uses stdout for '-')"
    )
    parser.add_argument(
        "-f", "--force", action="store_true", help="allow overwriting of existing file"
    )
    logging = parser.add_mutually_exclusive_group()
    logging.add_argument("-q", "--quiet", action="store_true", help="suppress logging output")
    logging.add_argument(
        "-v", "--verbose", action="store_true", help="enable verbose logging output"
    )
    parser.add_argument(
        "-i",
        "--indent",
        type=int,
        metavar="N",
        default=None,
        help="indentation using N spaces for the output file (defaults to none)",
    )
    parser.add_argument(
        "--reader",
        choices=("json", "xml", "auto"),
        default="auto",
        help="specify the input file format (either OSM XML or Overpass JSON/XML), defaults to auto-detect",
    )
    parser.add_argument(
        "--no-unused-filter",
        action="store_false",
        dest="filter_used_refs",
        help="keep elements that are only used as parts of other features "
        "(by default they are filtered out)",
    )
    parser.add_argument(
        "--areas",
        type=file,
        default=None,
        metavar="file",
        help="JSON file defining the keys that should be included from areas (uses defaults if omitted)",
    )
    parser.add_argument(
        "--polygons",
        type=file,
        default=None,
        metavar="file",
        help="JSON file defining the allowed/restricted polygon features (uses defaults if omitted)",
    )
    return parser


def detect_reader(infile: str, data: str) -> str:
    """Pick 'xml' or 'json' from the file extension, else sniff the content."""
    if infile.endswith((".osm", ".xml")):
        return "xml"
    if infile.endswith(".json"):
        return "json"
    head = data.lstrip()[:1]
    if head == "<":
        return "xml"
    if head in ("{", "["):
        return "json"
    return ""


def main(args=None) -> int:
    if args is None:
        args = sys.argv[1:]
    parser = setup_parser()
    args = parser.parse_args(args)

    if args.outfile != "-" and os.path.exists(args.outfile) and not args.force:
        print(
            f"Output file '{args.outfile}' already exists. Consider using -f to force overwriting.",
            file=sys.stderr,
        )
        return 1

    with open(args.infile, encoding="utf-8") as f:
        data = f.read()

    reader = args.reader if args.reader != "auto" else detect_reader(args.infile, data)
    if reader == "xml":
        parser_function = xml2geojson
    elif reader == "json":
        parser_function = json2geojson
    else:
        print("Auto-detecting input file format failed. Consider using --reader.", file=sys.stderr)
        return 1

    log_level = "WARNING"
    if args.quiet:
        log_level = "CRITICAL"
    elif args.verbose:
        log_level = "DEBUG"

    area_keys = None
    if args.areas:
        with open(args.areas, encoding="utf-8") as f:
            area_keys = json.load(f)
            if "areaKeys" in area_keys and len(area_keys) == 1:
                area_keys = area_keys["areaKeys"]
    polygon_features = None
    if args.polygons:
        with open(args.polygons, encoding="utf-8") as f:
            polygon_features = json.load(f)

    result = parser_function(
        data,
        filter_used_refs=args.filter_used_refs,
        log_level=log_level,
        area_keys=area_keys,
        polygon_features=polygon_features,
    )

    indent = args.indent
    if indent and indent < 0:
        indent = None
    if args.outfile == "-":
        # Windows consoles often default to a legacy code page (e.g. cp1252)
        # that cannot encode the UTF-8 text we emit
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        target = nullcontext(sys.stdout)
    else:
        target = open(args.outfile, "w", encoding="utf-8")

    with target as f:
        # ensure_ascii=False: keep non-ASCII text (names, descriptions) readable
        # instead of \uXXXX escapes
        print(json.dumps(result, indent=indent, ensure_ascii=False), file=f)
    return 0


if __name__ == "__main__":
    sys.exit(main())
