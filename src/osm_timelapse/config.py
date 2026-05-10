"""Configuration for the OSM Timelapse pipeline."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date
from enum import Enum, auto
from pathlib import Path


# Default center: Watkinsville, GA, USA
DEFAULT_CENTER = (33.835, -83.41)
DEFAULT_RADIUS_KM = 2.0

# Default date range
DEFAULT_START_DATE = date(2008, 1, 1)
DEFAULT_END_DATE = date(2024, 1, 1)


class RenderMode(Enum):
    ANIMATION = auto()
    TILES = auto()


@dataclass
class BBox:
    """Bounding box in WGS84 (lon/lat)."""

    west: float
    south: float
    east: float
    north: float

    def __str__(self) -> str:
        return f"{self.west},{self.south},{self.east},{self.north}"

    @classmethod
    def from_string(cls, s: str) -> BBox:
        """Parse 'west,south,east,north' string."""
        parts = [float(x.strip()) for x in s.split(",")]
        if len(parts) != 4:
            raise ValueError(f"Expected 4 comma-separated values, got {len(parts)}")
        return cls(west=parts[0], south=parts[1], east=parts[2], north=parts[3])

    @classmethod
    def from_center(cls, lat: float, lon: float, radius_km: float) -> BBox:
        import math
        # 1 degree of latitude is ~111.32 km
        lat_offset = radius_km / 111.32
        # 1 degree of longitude is ~111.32 km * cos(lat)
        lon_offset = radius_km / (111.32 * math.cos(math.radians(lat)))
        
        return cls(
            west=lon - lon_offset,
            south=lat - lat_offset,
            east=lon + lon_offset,
            north=lat + lat_offset,
        )

    def to_osmium_arg(self) -> str:
        """Format for osmium extract --bbox."""
        return f"{self.west},{self.south},{self.east},{self.north}"


@dataclass
class DatabaseConfig:
    """PostGIS database connection settings."""

    host: str = field(default_factory=lambda: os.environ.get("PGHOST", "db"))
    port: int = field(
        default_factory=lambda: int(os.environ.get("PGPORT", "5432"))
    )
    user: str = field(default_factory=lambda: os.environ.get("PGUSER", "renderer"))
    password: str = field(
        default_factory=lambda: os.environ.get("PGPASSWORD", "renderer")
    )
    database: str = field(
        default_factory=lambda: os.environ.get("PGDATABASE", "gis")
    )

    @property
    def dsn(self) -> str:
        return (
            f"host={self.host} port={self.port} "
            f"user={self.user} password={self.password} "
            f"dbname={self.database}"
        )


@dataclass
class RenderConfig:
    """Full pipeline configuration."""

    # Data directory (for downloading and caching history files)
    data_dir: Path = Path("/data")
    center: tuple[float, float] = DEFAULT_CENTER
    radius_km: float = DEFAULT_RADIUS_KM
    bbox: BBox = field(init=False)
    buffered_bbox: BBox = field(init=False)

    # Time range
    start_date: date = DEFAULT_START_DATE
    end_date: date = DEFAULT_END_DATE
    interval: str = "monthly"  # daily, weekly, monthly, quarterly, yearly

    # Rendering
    zoom: int = 13
    width: int = 1920
    height: int = 1080
    watermark: bool = True

    # Output
    output_dir: Path = Path("/output")
    frames_dir: Path = field(init=False)
    snapshots_dir: Path = field(init=False)
    output_video: Path = Path("/output/timelapse.mp4")
    fps: int = 10
    mode: RenderMode = RenderMode.ANIMATION
    tile_zooms: list[int] = field(default_factory=lambda: [13, 14, 15, 16])
    tiles_dir: Path = field(init=False)

    # Database
    db: DatabaseConfig = field(default_factory=DatabaseConfig)

    @property
    def cache_key(self) -> str:
        """Generate a unique cache key based on render parameters."""
        return f"c{self.center[0]}_{self.center[1]}_r{self.radius_km}_z{self.zoom}_{self.width}x{self.height}_wm{int(self.watermark)}"

    @property
    def location_key(self) -> str:
        """Generate a unique key based only on the geographic location."""
        return f"c{self.center[0]}_{self.center[1]}_r{self.radius_km}"

    # Paths inside the renderer container
    carto_style_dir: Path = Path("/opt/openstreetmap-carto")
    mapnik_xml: Path = Path("/opt/openstreetmap-carto/mapnik.xml")
    osm2pgsql_lua: Path = Path("/opt/openstreetmap-carto/openstreetmap-carto-flex.lua")
    flat_nodes: Path = Path("/tmp/flat-nodes.bin")

    def __post_init__(self) -> None:
        self.bbox = BBox.from_center(self.center[0], self.center[1], self.radius_km)
        # Extract 1.5km extra in all directions to ensure perfect tiles at the edges
        # (Mapnik labels and icons need a buffer around the render area)
        self.buffered_bbox = BBox.from_center(self.center[0], self.center[1], self.radius_km + 1.5)
        
        self.frames_dir = self.output_dir / "frames"
        self.snapshots_dir = self.output_dir / "snapshots" / self.location_key
        # Tiles are global (WGS84 XYZ) and can be shared across regions safely
        # because the buffered extraction ensures they are 'perfect'.
        self.tiles_dir = self.output_dir / "tiles"
        
        self.frames_dir.mkdir(parents=True, exist_ok=True)
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)
        self.tiles_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)

