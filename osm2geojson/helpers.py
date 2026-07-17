"""Helper utilities for osm2geojson."""

import urllib.parse
from time import sleep

import requests


OVERPASS = "https://overpass-api.de/api/interpreter/"
# overpass-api.de rejects generic client User-Agents (e.g. python-requests) with 406,
# and the usage policy asks clients to identify themselves
USER_AGENT = "osm2geojson (+https://github.com/rapkin/osm2geojson)"

# statuses worth retrying: rate limiting and transient server errors. Client
# errors (e.g. 400 for a malformed query) can never succeed - fail fast instead
# of hammering the public API.
RETRIABLE_STATUSES = {429, 500, 502, 503, 504}


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

    Retry behavior: rate limiting (429), transient server errors (5xx),
    timeouts and connection errors are retried; other client errors (e.g. 400
    for a malformed query) fail immediately.

    Returns:
        Response text from the Overpass API.

    Raises:
        requests.exceptions.HTTPError: If the server responds with a non-200
            status (immediately for non-retriable statuses, after the last
            attempt otherwise).
        requests.exceptions.ConnectionError: If connecting keeps failing.
        requests.exceptions.Timeout: If the server keeps not responding in time.
    """
    encoded = urllib.parse.quote(query.encode("utf-8"), safe="~()*!.'")
    error = None
    for attempt in range(retries + 1):
        if attempt > 0:
            sleep(retry_delay)
        try:
            r = requests.post(
                endpoint,
                data=f"data={encoded}",
                headers={
                    "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
                    "User-Agent": USER_AGENT,
                },
                timeout=timeout,
            )
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
            error = exc
            continue
        if r.status_code == 200:
            return r.text
        error = requests.exceptions.HTTPError(
            f"Overpass server respond with status {r.status_code}"
        )
        if r.status_code not in RETRIABLE_STATUSES:
            raise error
    raise error
