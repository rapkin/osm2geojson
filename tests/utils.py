"""Shared helpers for the test suite."""

import os


DATA_DIR = os.path.join(os.path.dirname(__file__), "data")


def read_data_file(name: str) -> str:
    """Read a file from tests/data and return its contents."""
    with open(os.path.join(DATA_DIR, name), encoding="utf-8") as f:
        return f.read()
