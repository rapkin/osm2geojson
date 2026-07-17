"""Tests for the osm2geojson CLI (python -m osm2geojson)."""

import json
import re
import subprocess
import sys
from pathlib import Path

from osm2geojson import xml2geojson
from osm2geojson.__main__ import detect_reader, main
from tests.utils import DATA_DIR, read_data_file


REPO_ROOT = Path(__file__).resolve().parents[1]
MAP_OSM = str(Path(DATA_DIR) / "map.osm")


def test_importing_module_does_not_run_cli():
    """__main__ must be importable (console script!) without executing the CLI."""
    result = subprocess.run(
        [sys.executable, "-c", "import osm2geojson.__main__; print('imported ok')"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "imported ok"


def test_module_invocation_end_to_end(tmp_path):
    out_file = tmp_path / "node.geojson"
    result = subprocess.run(
        [sys.executable, "-m", "osm2geojson", str(Path(DATA_DIR) / "node.osm"), str(out_file)],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(out_file.read_text(encoding="utf-8"))["type"] == "FeatureCollection"


def test_cli_output_keeps_unicode_readable(tmp_path):
    """Non-ASCII tag values must be written as UTF-8 text, not \\uXXXX escapes."""
    out_file = tmp_path / "map.geojson"
    assert main([MAP_OSM, str(out_file)]) == 0

    text = out_file.read_text(encoding="utf-8")
    assert "Драгоманова вулиця" in text
    assert "\\u0" not in text

    # and the content still matches the library output
    assert json.loads(text) == xml2geojson(read_data_file("map.osm"))


def test_cli_stdout_keeps_unicode_readable(capsys):
    assert main([MAP_OSM, "-"]) == 0
    out = capsys.readouterr().out
    assert "Драгоманова вулиця" in out
    assert json.loads(out)["type"] == "FeatureCollection"


def test_cli_refuses_overwrite_without_force(tmp_path, capsys):
    out_file = tmp_path / "out.geojson"
    out_file.write_text("occupied")
    assert main([MAP_OSM, str(out_file)]) == 1
    assert "already exists" in capsys.readouterr().err
    assert main([MAP_OSM, str(out_file), "-f"]) == 0


def test_reader_auto_detection():
    assert detect_reader("map.osm", "") == "xml"
    assert detect_reader("map.json", "") == "json"
    assert detect_reader("data.txt", "  <osm></osm>") == "xml"
    assert detect_reader("data.txt", '\n{"elements": []}') == "json"
    assert detect_reader("data.txt", "not osm data") == ""


def test_data_files_have_no_unicode_escapes():
    """Checked-in expected outputs stay human-readable (see test_cli above)."""
    escape = re.compile(r"\\u[0-9a-fA-F]{4}")
    offenders = [
        path.name
        for path in Path(DATA_DIR).glob("*.geojson")
        if escape.search(path.read_text(encoding="utf-8"))
    ]
    assert not offenders, f"files with \\uXXXX escapes: {offenders}"
