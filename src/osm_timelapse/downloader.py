"""Download OSM full-history data from Geofabrik Internal.

Uses Geofabrik's internal download server (osm-internal.download.geofabrik.de)
to download regional full-history .osh.pbf files. Requires an OpenStreetMap
account for authentication via OAuth2.

Authentication flow:
1. User provides OSM username/password via env vars or a settings file
2. We perform the OAuth2 dance with openstreetmap.org
3. We get a session cookie for osm-internal.download.geofabrik.de
4. We download the regional history file using that cookie
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import sys
import urllib.parse
from pathlib import Path

import requests

from osm_timelapse.config import BBox

log = logging.getLogger(__name__)

GEOFABRIK_INDEX_URL = "https://download.geofabrik.de/index-v1.json"
GEOFABRIK_COOKIE_ENDPOINT = "https://osm-internal.download.geofabrik.de/get_cookie"
OSM_HOST = "https://www.openstreetmap.org"
CUSTOM_HEADER = {"user-agent": "osm-timelapse/0.1.0"}


# ---------------------------------------------------------------------------
# OAuth2 cookie retrieval (adapted from Geofabrik's oauth_cookie_client.py)
# ---------------------------------------------------------------------------


def _find_authenticity_token(html: str) -> str:
    """Extract the CSRF authenticity token from an OSM HTML page."""
    pattern = r'name="csrf-token" content="([^"]+)"'
    m = re.search(pattern, html)
    if m is None:
        raise RuntimeError("Could not find authenticity_token in OSM login page")
    return m.group(1)


def get_geofabrik_cookie(
    username: str,
    password: str,
    cookie_file: Path | None = None,
) -> str:
    """Perform the OAuth2 flow to get a Geofabrik session cookie.

    Args:
        username: OpenStreetMap username.
        password: OpenStreetMap password.
        cookie_file: Optional path to cache the cookie.

    Returns:
        Cookie string in Netscape format suitable for wget/curl.
    """
    # Check for cached cookie
    if cookie_file and cookie_file.exists():
        cookie_text = cookie_file.read_text().strip()
        if cookie_text:
            log.info("Using cached Geofabrik cookie from %s", cookie_file)
            return cookie_text

    log.info("Authenticating with OpenStreetMap for Geofabrik access...")

    # Step 1: Get authorization URL from Geofabrik
    url = GEOFABRIK_COOKIE_ENDPOINT + "?action=get_authorization_url"
    r = requests.post(url, data={}, headers=CUSTOM_HEADER, timeout=30)
    r.raise_for_status()
    json_resp = r.json()

    authorization_url = json_resp["authorization_url"]
    state = json_resp["state"]
    redirect_uri = json_resp["redirect_uri"]
    client_id = json_resp["client_id"]

    # Step 2: Log in to OSM
    s = requests.Session()
    login_page = s.get(
        OSM_HOST + "/login?cookie_test=true",
        headers=CUSTOM_HEADER,
        timeout=30,
    )
    login_page.raise_for_status()

    token = _find_authenticity_token(login_page.text)
    login_resp = s.post(
        OSM_HOST + "/login",
        data={
            "username": username,
            "password": password,
            "referer": "/",
            "commit": "Login",
            "authenticity_token": token,
        },
        headers=CUSTOM_HEADER,
        allow_redirects=False,
        timeout=30,
    )
    if login_resp.status_code != 302:
        raise RuntimeError(
            f"OSM login failed (status {login_resp.status_code}). "
            "Check your OSM_USERNAME and OSM_PASSWORD."
        )

    # Step 3: Authorize the Geofabrik OAuth app
    auth_resp = s.get(
        authorization_url,
        headers=CUSTOM_HEADER,
        allow_redirects=False,
        timeout=30,
    )
    if auth_resp.status_code == 200:
        # First time: need to submit the authorization form
        token = _find_authenticity_token(auth_resp.text)
        auth_resp = s.post(
            authorization_url,
            data={
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "authenticity_token": token,
                "state": state,
                "response_type": "code",
                "scope": "read_prefs",
                "nonce": "",
                "code_challenge": "",
                "code_challenge_method": "",
                "commit": "Authorize",
            },
            headers=CUSTOM_HEADER,
            allow_redirects=False,
            timeout=30,
        )
    if auth_resp.status_code != 302:
        raise RuntimeError(
            f"OAuth authorization failed (status {auth_resp.status_code})"
        )

    location = auth_resp.headers.get("location", "")
    if "?" not in location:
        raise RuntimeError("OAuth redirect URL missing query string")

    # Step 4: Log out of OSM
    s.get(OSM_HOST + "/logout", headers=CUSTOM_HEADER, timeout=30)

    # Step 5: Exchange code for cookie
    cookie_url = f"{location}&{urllib.parse.urlencode({'format': 'netscape'})}"
    cookie_resp = requests.get(cookie_url, headers=CUSTOM_HEADER, timeout=30)
    cookie_text = cookie_resp.text.strip()

    # Cache the cookie
    if cookie_file:
        cookie_file.parent.mkdir(parents=True, exist_ok=True)
        cookie_file.write_text(cookie_text + "\n")
        log.info("Cookie cached to %s", cookie_file)

    log.info("Authentication successful!")
    return cookie_text


def get_osm_credentials() -> tuple[str, str]:
    """Get OSM credentials from environment variables.

    Returns:
        (username, password) tuple.

    Raises:
        SystemExit if credentials are not configured.
    """
    username = os.environ.get("OSM_USERNAME", "")
    password = os.environ.get("OSM_PASSWORD", "")

    if not username or not password:
        log.error(
            "OSM credentials not found. Set these environment variables:\n"
            "  OSM_USERNAME=your_osm_username\n"
            "  OSM_PASSWORD=your_osm_password\n"
            "\n"
            "You can set them in a .env file or pass them via docker compose."
        )
        sys.exit(1)

    return username, password


# ---------------------------------------------------------------------------
# Geofabrik region lookup
# ---------------------------------------------------------------------------


def _bbox_contains_point(bbox: BBox, lon: float, lat: float) -> bool:
    """Check if a bbox contains a point."""
    return (bbox.west <= lon <= bbox.east) and (bbox.south <= lat <= bbox.north)


def _bbox_intersects(a: BBox, b: BBox) -> bool:
    """Check if two bounding boxes intersect."""
    return not (
        a.east < b.west or a.west > b.east or
        a.north < b.south or a.south > b.north
    )


def _bbox_area(bbox: BBox) -> float:
    """Approximate area of a bbox in square degrees."""
    return (bbox.east - bbox.west) * (bbox.north - bbox.south)


def find_best_geofabrik_region(
    target_bbox: BBox,
    cache_dir: Path,
) -> dict:
    """Find the smallest Geofabrik region that contains the target bbox.

    Downloads and caches the Geofabrik region index (with geometries/bboxes),
    then finds the smallest region whose bounding box fully contains our target.

    Args:
        target_bbox: The bounding box we want data for.
        cache_dir: Directory to cache the Geofabrik index.

    Returns:
        Dict with region properties including 'history' URL.
    """
    # Download/cache the index
    index_file = cache_dir / "geofabrik-index.json"
    if not index_file.exists():
        log.info("Downloading Geofabrik region index...")
        r = requests.get(GEOFABRIK_INDEX_URL, headers=CUSTOM_HEADER, timeout=60)
        r.raise_for_status()
        cache_dir.mkdir(parents=True, exist_ok=True)
        index_file.write_text(r.text)
        log.info("Index cached to %s", index_file)

    with open(index_file) as f:
        index = json.load(f)

    # Find all regions that contain our bbox and have a history URL
    candidates = []
    for feature in index["features"]:
        props = feature["properties"]
        urls = props.get("urls", {})
        if "history" not in urls:
            continue

        # Use the feature's bbox from GeoJSON (if present)
        geom_bbox = feature.get("bbox")
        if geom_bbox and len(geom_bbox) == 4:
            region_bbox = BBox(
                west=geom_bbox[0], south=geom_bbox[1],
                east=geom_bbox[2], north=geom_bbox[3],
            )
        elif feature.get("geometry"):
            # Compute bbox from geometry coordinates
            coords = _extract_coords(feature["geometry"])
            if not coords:
                continue
            lons = [c[0] for c in coords]
            lats = [c[1] for c in coords]
            region_bbox = BBox(
                west=min(lons), south=min(lats),
                east=max(lons), north=max(lats),
            )
        else:
            continue

        # Check if this region fully contains our target bbox
        if (region_bbox.west <= target_bbox.west and
            region_bbox.south <= target_bbox.south and
            region_bbox.east >= target_bbox.east and
            region_bbox.north >= target_bbox.north):
            area = _bbox_area(region_bbox)
            candidates.append((area, props))

    if not candidates:
        log.error(
            "No Geofabrik region found containing bbox %s. "
            "You may need to download the planet history file manually.",
            target_bbox,
        )
        sys.exit(1)

    # Sort by area (smallest first) — we want the most specific region
    candidates.sort(key=lambda x: x[0])
    best = candidates[0][1]
    log.info(
        "Best matching Geofabrik region: %s (%s)",
        best["name"],
        best["id"],
    )
    return best


def _extract_coords(geometry: dict) -> list[tuple[float, float]]:
    """Recursively extract all coordinate pairs from a GeoJSON geometry."""
    coords = []
    geom_type = geometry.get("type", "")
    raw_coords = geometry.get("coordinates", [])

    if geom_type == "Point":
        coords.append(tuple(raw_coords[:2]))
    elif geom_type in ("LineString", "MultiPoint"):
        coords.extend(tuple(c[:2]) for c in raw_coords)
    elif geom_type in ("Polygon", "MultiLineString"):
        for ring in raw_coords:
            coords.extend(tuple(c[:2]) for c in ring)
    elif geom_type == "MultiPolygon":
        for polygon in raw_coords:
            for ring in polygon:
                coords.extend(tuple(c[:2]) for c in ring)
    return coords


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------


def download_with_cookie(
    url: str,
    cookie_text: str,
    output_file: Path,
) -> Path:
    """Download a file using an authenticated Geofabrik cookie.

    Args:
        url: URL to download.
        cookie_text: Netscape-format cookie string.
        output_file: Where to save the download.

    Returns:
        Path to the downloaded file.
    """
    output_file.parent.mkdir(parents=True, exist_ok=True)

    # Write cookie to a temp file for wget/curl
    cookie_jar = output_file.parent / ".geofabrik-cookie.txt"
    cookie_jar.write_text(cookie_text + "\n")

    log.info("Downloading: %s", url)
    log.info("Output:      %s", output_file)

    if shutil.which("wget"):
        cmd = [
            "wget",
            "--load-cookies", str(cookie_jar),
            "--continue",
            "--progress=bar:force",
            "--tries=0",
            "--timeout=60",
            "-O", str(output_file),
            url,
        ]
    elif shutil.which("curl"):
        cmd = [
            "curl",
            "-L",
            "-b", str(cookie_jar),
            "-C", "-",
            "-o", str(output_file),
            url,
        ]
    else:
        log.error("Neither wget nor curl found. Cannot download.")
        sys.exit(1)

    log.info("Running: %s", " ".join(cmd))
    subprocess.run(cmd, check=True)

    # Clean up cookie file
    cookie_jar.unlink(missing_ok=True)

    size_mb = output_file.stat().st_size / (1024**2)
    log.info("Download complete: %s (%.1f MB)", output_file, size_mb)
    return output_file


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def ensure_history_data(
    data_dir: Path,
    bbox: str,
) -> Path:
    """Ensure we have a regional history file for the given bounding box.

    This is the main entry point. It:
    1. Checks for existing .osh.pbf files in data_dir
    2. If none found, looks up the best Geofabrik region for the bbox
    3. Authenticates with OSM and downloads the regional history file
    4. Optionally extracts just the bbox from the regional file

    Args:
        data_dir: Base data directory for caching.
        bbox: Bounding box string "west,south,east,north".

    Returns:
        Path to the regional .osh.pbf history file.
    """
    target_bbox = BBox.from_string(bbox)
    data_dir.mkdir(parents=True, exist_ok=True)

    # Check if there's already a .osh.pbf file in data_dir
    existing = list(data_dir.glob("*.osh.pbf"))
    if existing:
        # Use the first one found
        log.info("Found existing history file: %s", existing[0])
        return existing[0]

    # Look up the best Geofabrik region
    region = find_best_geofabrik_region(target_bbox, data_dir)
    history_url = region["urls"]["history"]
    region_id = region["id"]
    region_filename = f"{region_id}.osh.pbf"
    region_file = data_dir / region_filename

    if not region_file.exists():
        # Authenticate and download
        log.info("=" * 60)
        log.info("Downloading history for: %s", region["name"])
        log.info("URL: %s", history_url)
        log.info("This may take a while depending on region size.")
        log.info("=" * 60)

        username, password = get_osm_credentials()
        cookie = get_geofabrik_cookie(
            username=username,
            password=password,
            cookie_file=data_dir / ".geofabrik-cookie.txt",
        )
        download_with_cookie(history_url, cookie, region_file)
    else:
        log.info("Regional history file already downloaded: %s", region_file)

    # Now extract just the requested bounding box
    import hashlib
    bbox_hash = hashlib.md5(bbox.encode()).hexdigest()[:8]
    extract_file = data_dir / f"extract_{bbox_hash}.osh.pbf"

    if extract_file.exists():
        log.info("Bounding box extract already exists: %s", extract_file)
        return extract_file

    log.info("Extracting bounding box %s from %s...", bbox, region_filename)
    if shutil.which("osmium") is None:
        log.error("osmium tool not found on PATH. Cannot extract bounding box.")
        sys.exit(1)

    cmd = [
        "osmium", "extract",
        "--bbox", bbox,
        "--with-history",
        "-o", str(extract_file),
        "--overwrite",
        str(region_file),
    ]
    log.info("Running: %s", " ".join(cmd))
    subprocess.run(cmd, check=True)

    log.info("Bounding box extracted to: %s", extract_file)
    return extract_file

