"""Helper utilities for osm2geojson."""

import urllib
from time import sleep

import requests


OVERPASS = "https://overpass-api.de/api/interpreter/"
# overpass-api.de rejects generic client User-Agents (e.g. python-requests) with 406,
# and the usage policy asks clients to identify themselves
USER_AGENT = "osm2geojson (+https://github.com/rapkin/osm2geojson)"


def overpass_call(
    query: str,
    *,
    endpoint: str = OVERPASS,
    timeout: float = 180,
    retries: int = 5,
    retry_delay: float = 5,
) -> str:
    """Call the Overpass API with the given query.

    Args:
        query: Overpass QL query string.
        endpoint: Overpass API endpoint URL (defaults to overpass-api.de).
        timeout: Timeout in seconds for each HTTP request (Overpass queries can
            legitimately run long; raise this for heavy queries).
        retries: Number of retries after a failed attempt (0 disables retrying).
        retry_delay: Seconds to sleep between attempts.

    Returns:
        Response text from the Overpass API.

    Raises:
        requests.exceptions.HTTPError: If the server returns a non-200 status
            on the last attempt.
        requests.exceptions.Timeout: If the server does not respond in time.
    """
    encoded = urllib.parse.quote(query.encode("utf-8"), safe="~()*!.'")
    status = None
    for attempt in range(retries + 1):
        if attempt > 0:
            sleep(retry_delay)
        r = requests.post(
            endpoint,
            data=f"data={encoded}",
            headers={
                "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
                "User-Agent": USER_AGENT,
            },
            timeout=timeout,
        )
        if r.status_code == 200:
            return r.text
        status = r.status_code
    raise requests.exceptions.HTTPError(f"Overpass server respond with status {status}")
