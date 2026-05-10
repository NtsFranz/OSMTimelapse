"""Tile math utilities for converting geographic coordinates to Mapnik envelopes."""

from __future__ import annotations

import math
from dataclasses import dataclass

from osm_timelapse.config import BBox


# EPSG:3857 (Web Mercator) constants
EARTH_CIRCUMFERENCE = 20037508.342789244  # half of the full circumference in meters


@dataclass
class MercatorEnvelope:
    """A bounding box in EPSG:3857 (Web Mercator) coordinates."""

    xmin: float
    ymin: float
    xmax: float
    ymax: float


def lonlat_to_mercator(lon: float, lat: float) -> tuple[float, float]:
    """Convert WGS84 lon/lat to EPSG:3857 Web Mercator x/y."""
    x = lon * EARTH_CIRCUMFERENCE / 180.0
    y = math.log(math.tan((90.0 + lat) * math.pi / 360.0)) / math.pi
    y = y * EARTH_CIRCUMFERENCE
    return x, y


def bbox_to_mercator(bbox: BBox) -> MercatorEnvelope:
    """Convert a WGS84 bounding box to a Mercator envelope."""
    xmin, ymin = lonlat_to_mercator(bbox.west, bbox.south)
    xmax, ymax = lonlat_to_mercator(bbox.east, bbox.north)
    return MercatorEnvelope(xmin=xmin, ymin=ymin, xmax=xmax, ymax=ymax)


def compute_pixel_dimensions(
    bbox: BBox,
    zoom: int,
    tile_size: int = 256,
) -> tuple[int, int]:
    """Compute the pixel dimensions needed to render a bbox at a given zoom.

    This calculates how many pixels the bounding box spans at the given zoom
    level, which can be used as an alternative to a fixed width/height.

    Returns:
        (width, height) in pixels.
    """
    # Number of tiles at this zoom level
    n = 2**zoom

    # Convert bbox to tile coordinates (fractional)
    def lon_to_tile_x(lon: float) -> float:
        return (lon + 180.0) / 360.0 * n

    def lat_to_tile_y(lat: float) -> float:
        lat_rad = math.radians(lat)
        return (1.0 - math.log(math.tan(lat_rad) + 1.0 / math.cos(lat_rad)) / math.pi) / 2.0 * n

    x_min = lon_to_tile_x(bbox.west)
    x_max = lon_to_tile_x(bbox.east)
    y_min = lat_to_tile_y(bbox.north)  # Note: y is inverted in tile coords
    y_max = lat_to_tile_y(bbox.south)

    width = int(abs(x_max - x_min) * tile_size)
    height = int(abs(y_max - y_min) * tile_size)

    # Ensure minimum size
    width = max(width, tile_size)
    height = max(height, tile_size)

    return width, height


def lonlat_to_tile(lon: float, lat: float, zoom: int) -> tuple[int, int]:
    """Convert lon/lat to integer tile coordinates at a given zoom."""
    lat_rad = math.radians(lat)
    n = 2.0**zoom
    xtile = int((lon + 180.0) / 360.0 * n)
    ytile = int((1.0 - math.log(math.tan(lat_rad) + (1 / math.cos(lat_rad))) / math.pi) / 2.0 * n)
    return xtile, ytile


def tile_to_bbox(x: int, y: int, zoom: int) -> BBox:
    """Returns the WGS84 bounding box for a given XYZ tile."""
    n = 2.0**zoom
    lon_west = x / n * 360.0 - 180.0
    lon_east = (x + 1) / n * 360.0 - 180.0
    lat_north_rad = math.atan(math.sinh(math.pi * (1 - 2 * y / n)))
    lat_south_rad = math.atan(math.sinh(math.pi * (1 - 2 * (y + 1) / n)))
    return BBox(
        west=lon_west,
        south=math.degrees(lat_south_rad),
        east=lon_east,
        north=math.degrees(lat_north_rad),
    )
