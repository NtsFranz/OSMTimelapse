"""Core pipeline — orchestrates osmium, osm2pgsql, Mapnik, and ffmpeg."""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

from osm_timelapse.config import RenderConfig, RenderMode
from osm_timelapse.dates import format_iso, generate_dates
from osm_timelapse.downloader import ensure_history_data
from osm_timelapse.tile_math import (
    bbox_to_mercator,
    compute_pixel_dimensions,
    lonlat_to_tile,
    tile_to_bbox,
)

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(
    cmd: list[str], *, check: bool = True, **kwargs
) -> subprocess.CompletedProcess:
    """Run a subprocess, logging the command."""
    log.info("Running: %s", " ".join(cmd))
    return subprocess.run(cmd, check=check, **kwargs)


def _require_tool(name: str) -> None:
    """Raise if a required CLI tool is not on PATH."""
    if shutil.which(name) is None:
        log.error("Required tool %r not found on PATH", name)
        sys.exit(1)


def _run_with_spinner(title: str, cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    """Run a command with a 'gum spin' spinner, without logging the internal command."""
    if shutil.which("gum") is None:
        return _run(cmd, **kwargs)

    # Wrap the command in 'gum spin'
    spin_cmd = ["gum", "spin", "--spinner", "dot", "--title", title, "--"] + cmd
    
    # We don't log the internal command here to keep the output clean
    return subprocess.run(spin_cmd, check=True, **kwargs)




# ---------------------------------------------------------------------------
# Stage 1: Ensure data is available (download + extract if needed)
# ---------------------------------------------------------------------------


def ensure_data(cfg: RenderConfig) -> Path:
    """Ensure we have a regional history file for the configured bbox.

    Downloads the planet history file and extracts the region automatically
    if no suitable data is found in the data directory.

    Returns the path to the regional .osh.pbf file.
    """
    return ensure_history_data(
        data_dir=cfg.data_dir,
        bbox=cfg.buffered_bbox.to_osmium_arg(),
    )


# ---------------------------------------------------------------------------
# Stage 2: Generate point-in-time snapshots
# ---------------------------------------------------------------------------


def generate_snapshot(
    history_file: Path,
    target_date: date,
    output_file: Path,
) -> Path:
    """Use osmium time-filter to create a snapshot .osm.pbf at a given date.

    Returns the path to the snapshot file.
    """
    _require_tool("osmium")

    if output_file.exists():
        log.info("Snapshot already exists: %s", output_file)
        return output_file

    iso = format_iso(target_date)
    cmd = [
        "osmium",
        "time-filter",
        str(history_file),
        iso,
        "-o",
        str(output_file),
        "--overwrite",
    ]
    log.info("Creating snapshot for %s...", iso)
    _run(cmd)
    log.info("Snapshot created for %s: %s", target_date, output_file)
    return output_file


def generate_all_snapshots(
    cfg: RenderConfig,
    history_file: Path,
) -> list[tuple[date, Path]]:
    """Generate snapshots for all dates in the configured range.

    Args:
        cfg: Render configuration.
        history_file: Path to the regional .osh.pbf history file.

    Returns a list of (date, snapshot_path) tuples.
    """
    snapshots: list[tuple[date, Path]] = []

    for d in generate_dates(cfg.start_date, cfg.end_date, cfg.interval):
        filename = f"snapshot_{d.isoformat()}.osm.pbf"
        output = cfg.snapshots_dir / filename
        generate_snapshot(history_file, d, output)
        snapshots.append((d, output))

    log.info("Generated %d snapshots", len(snapshots))
    return snapshots


# ---------------------------------------------------------------------------
# Stage 3: Import snapshot into PostGIS
# ---------------------------------------------------------------------------


def import_snapshot(cfg: RenderConfig, snapshot_file: Path) -> None:
    """Import a .osm.pbf snapshot into PostGIS using osm2pgsql.

    This does a full (create mode) import, replacing any existing data.
    """
    _require_tool("osm2pgsql")

    if not snapshot_file.exists():
        log.error("Snapshot file not found: %s", snapshot_file)
        sys.exit(1)
    
    size_mb = snapshot_file.stat().st_size / (1024 * 1024)
    log.info("Snapshot file size: %.2f MB", size_mb)
    if size_mb < 0.001:
        log.warning("Snapshot file is nearly empty! This might be why the output is blank.")

    if not cfg.osm2pgsql_lua.exists():
        log.error("osm2pgsql lua script not found: %s", cfg.osm2pgsql_lua)
        sys.exit(1)

    cmd = [
        "osm2pgsql",
        "-O",
        "flex",
        "-S",
        str(cfg.osm2pgsql_lua),
        "--slim",
        "--drop",
        "--host",
        cfg.db.host,
        "--port",
        str(cfg.db.port),
        "--username",
        cfg.db.user,
        "--database",
        cfg.db.database,
        "--number-processes",
        str(__import__("multiprocessing").cpu_count()),
        str(snapshot_file),
    ]

    env = dict(__import__("os").environ)
    env["PGPASSWORD"] = cfg.db.password

    log.info("Importing %s to DB using flex mode...", snapshot_file.name)
    _run(cmd, env=env)
    log.info("Imported %s into PostGIS", snapshot_file)

    # Run post-import SQL indexes if they exist
    # Note: For small regional extracts, building these indexes takes longer
    # than the rendering speedup they provide. Skipping to save ~1s per frame.
    # indexes_sql = cfg.carto_style_dir / "indexes.sql"
    # if indexes_sql.exists():
    #     _run_psql(cfg, indexes_sql)


def _run_psql_command(cfg: RenderConfig, sql_cmd: str) -> None:
    """Run a SQL command string against the PostGIS database."""
    cmd = [
        "psql",
        "-h",
        cfg.db.host,
        "-p",
        str(cfg.db.port),
        "-U",
        cfg.db.user,
        "-d",
        cfg.db.database,
        "-c",
        sql_cmd,
    ]
    env = dict(__import__("os").environ)
    env["PGPASSWORD"] = cfg.db.password
    _run(cmd, env=env)


def _run_psql(cfg: RenderConfig, sql_file: Path) -> None:
    """Run a SQL file against the PostGIS database."""
    cmd = [
        "psql",
        "-h",
        cfg.db.host,
        "-p",
        str(cfg.db.port),
        "-U",
        cfg.db.user,
        "-d",
        cfg.db.database,
        "-f",
        str(sql_file),
    ]
    env = dict(__import__("os").environ)
    env["PGPASSWORD"] = cfg.db.password
    _run(cmd, env=env)


# ---------------------------------------------------------------------------
# Stage 4: Render a frame with Mapnik
# ---------------------------------------------------------------------------


def render_frame(cfg: RenderConfig, output_file: Path, m: "mapnik.Map" = None) -> Path:
    """Render the current PostGIS database state to a PNG image using Mapnik.

    Uses the openstreetmap-carto mapnik.xml style.
    Returns the path to the rendered image.
    """
    try:
        import mapnik
    except ImportError:
        log.error(
            "python3-mapnik is not installed. "
            "This must run inside the renderer Docker container."
        )
        sys.exit(1)

    envelope = bbox_to_mercator(cfg.bbox)

    # Determine target dimensions
    width, height = cfg.width, cfg.height
    if (width == 0 or height == 0) and cfg.zoom is not None:
        width, height = compute_pixel_dimensions(cfg.bbox, cfg.zoom)
    
    # Defaults if still 0
    if width == 0: width = 1920
    if height == 0: height = 1080

    if m is None:
        m = mapnik.Map(width, height)
        mapnik.load_map(m, str(cfg.mapnik_xml))
    else:
        m.resize(width, height)

    # Set the map extent to our bounding box in mercator coordinates
    m.zoom_to_box(
        mapnik.Box2d(envelope.xmin, envelope.ymin, envelope.xmax, envelope.ymax)
    )

    mapnik.render_to_file(m, str(output_file), "png256")
    log.info("Rendered frame: %s (%dx%d)", output_file, width, height)
    return output_file


def render_tiles(cfg: RenderConfig, m: "mapnik.Map", snapshot_date: date) -> None:
    """Render a tile pyramid (XYZ) for the given snapshot and zoom levels.

    Uses a 'meta-tile' approach: rendering multiple tiles in a single larger image
    to minimize database query overhead, which is the primary bottleneck.
    """
    import mapnik
    from PIL import Image
    from osm_timelapse.config import BBox

    snapshot_str = snapshot_date.isoformat()
    # Number of tiles per side in a meta-tile block (e.g., 16x16 = 256 tiles)
    # 16x16 is the maximum recommended size to balance DB efficiency and RAM usage.
    META_SIZE = 16

    for zoom in cfg.tile_zooms:
        x1, y1 = lonlat_to_tile(cfg.bbox.west, cfg.bbox.north, zoom)
        x2, y2 = lonlat_to_tile(cfg.bbox.east, cfg.bbox.south, zoom)

        total_tiles = (x2 - x1 + 1) * (y2 - y1 + 1)
        log.info("  Zoom %d: Processing %d tiles...", zoom, total_tiles)

        for mx in range(x1, x2 + 1, META_SIZE):
            for my in range(y1, y2 + 1, META_SIZE):
                mx_end = min(mx + META_SIZE - 1, x2)
                my_end = min(my + META_SIZE - 1, y2)

                # Check if we actually need to render anything in this meta-tile
                needs_render = False
                for x in range(mx, mx_end + 1):
                    for y in range(my, my_end + 1):
                        tile_file = (
                            cfg.tiles_dir
                            / snapshot_str
                            / str(zoom)
                            / str(x)
                            / f"{y}.png"
                        )
                        if not tile_file.exists():
                            needs_render = True
                            break
                    if needs_render:
                        break

                if not needs_render:
                    continue

                # Calculate dimensions and bbox for the whole meta-tile
                tiles_w = mx_end - mx + 1
                tiles_h = my_end - my + 1

                bbox_nw = tile_to_bbox(mx, my, zoom)
                bbox_se = tile_to_bbox(mx_end, my_end, zoom)

                # Combine into a single meta-bbox
                meta_bbox = BBox(
                    west=bbox_nw.west,
                    south=bbox_se.south,
                    east=bbox_se.east,
                    north=bbox_nw.north,
                )
                envelope = bbox_to_mercator(meta_bbox)

                m.resize(tiles_w * 256, tiles_h * 256)
                m.zoom_to_box(
                    mapnik.Box2d(
                        envelope.xmin, envelope.ymin, envelope.xmax, envelope.ymax
                    )
                )

                # Render to an in-memory image to avoid disk I/O
                im = mapnik.Image(tiles_w * 256, tiles_h * 256)
                mapnik.render(m, im)

                # Convert mapnik image (RGBA) to PIL image
                meta_img = Image.frombytes(
                    "RGBA", (tiles_w * 256, tiles_h * 256), im.tostring()
                )

                # Slice the meta-tile into individual tiles
                for x in range(mx, mx_end + 1):
                    for y in range(my, my_end + 1):
                        tile_dir = cfg.tiles_dir / snapshot_str / str(zoom) / str(x)
                        tile_dir.mkdir(parents=True, exist_ok=True)
                        tile_file = tile_dir / f"{y}.png"

                        if tile_file.exists():
                            continue

                        # Crop and save
                        left = (x - mx) * 256
                        top = (y - my) * 256
                        tile_img = meta_img.crop((left, top, left + 256, top + 256))

                        # Convert to Paletted (png256) to save space, matching mapnik's output
                        tile_img.convert("P", palette=Image.ADAPTIVE).save(
                            tile_file, "PNG"
                        )


def save_tile_metadata(cfg: RenderConfig, snapshots: list[tuple[date, Path]]) -> None:
    """Save metadata.json for the web viewer."""
    import json

    metadata = {
        "dates": [d.isoformat() for d, _ in snapshots],
        "center": list(cfg.center),
        "default_zoom": cfg.zoom,
        "bbox": [cfg.bbox.west, cfg.bbox.south, cfg.bbox.east, cfg.bbox.north],
    }
    metadata_file = cfg.tiles_dir / "metadata.json"
    with open(metadata_file, "w") as f:
        json.dump(metadata, f, indent=2)
    log.info("Saved viewer metadata: %s", metadata_file)


def add_watermark(image_path: Path, text: str) -> None:
    """Burn a date watermark into the bottom-left corner of a rendered frame."""
    from PIL import Image, ImageDraw, ImageFont

    img = Image.open(image_path).convert("RGBA")
    draw = ImageDraw.Draw(img)

    # Try to use a nice font, fall back to default
    font_size = max(20, img.height // 30)
    try:
        font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size
        )
    except (OSError, IOError):
        font = ImageFont.load_default()

    # Semi-transparent background for readability
    # Use a fixed width based on the longest possible date string to prevent the box from shifting
    sample_text = "September 2026"  # Longest month + likely year
    sample_bbox = draw.textbbox((0, 0), sample_text, font=font)
    box_w = (sample_bbox[2] - sample_bbox[0]) + 20
    
    text_bbox = draw.textbbox((0, 0), text, font=font)
    text_h = text_bbox[3] - text_bbox[1]
    
    padding = 10
    x = padding
    y = img.height - text_h - padding * 2

    # Draw background rectangle with fixed width
    draw.rectangle(
        [0, y - padding, box_w, img.height],
        fill=(0, 0, 0, 180),
    )
    draw.text((x, y), text, fill=(255, 255, 255, 255), font=font)

    img.save(image_path)
    log.info("Added watermark: %s", text)


# ---------------------------------------------------------------------------
# Stage 5: Assemble video from frames
# ---------------------------------------------------------------------------


def assemble_video(cfg: RenderConfig) -> Path:
    """Use ffmpeg to assemble rendered frames into a timelapse video.

    Returns the path to the output video.
    """
    _require_tool("ffmpeg")

    cache_key = cfg.cache_key

    # Frames are named frame_YYYY-MM-DD_CACHEKEY.png — sort by name for chronological order
    pattern = str(cfg.frames_dir / f"frame_*_{cache_key}.png")

    # Build a concat file for ffmpeg (more reliable than glob with varying names)
    concat_file = cfg.output_dir / "frames.txt"
    frame_files = sorted(cfg.frames_dir.glob(f"frame_*_{cache_key}.png"))
    if not frame_files:
        log.error("No frames found in %s", cfg.frames_dir)
        sys.exit(1)

    with open(concat_file, "w") as f:
        for frame in frame_files:
            # Each frame shown for 1/fps seconds
            f.write(f"file '{frame}'\n")
            f.write(f"duration {1.0 / cfg.fps}\n")
        # Repeat last frame to avoid ffmpeg cutting it short
        f.write(f"file '{frame_files[-1]}'\n")

    cmd = [
        "ffmpeg",
        "-y",  # Overwrite output
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_file),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-vf",
        f"fps={cfg.fps}",
        str(cfg.output_video),
    ]
    _run(cmd)
    log.info("Video created: %s", cfg.output_video)
    return cfg.output_video


# ---------------------------------------------------------------------------
# Full pipeline
# ---------------------------------------------------------------------------


def setup_external_data(cfg: RenderConfig) -> None:
    """Download external shapefiles and load them into PostGIS."""
    log.info("Ensuring external shapefile data is loaded into PostGIS...")

    cmd = [
        "python3",
        "/opt/openstreetmap-carto/scripts/get-external-data.py",
        "-H",
        cfg.db.host,
        "-p",
        str(cfg.db.port),
        "-d",
        cfg.db.database,
        "-U",
        cfg.db.user,
        "-c",
        "/opt/openstreetmap-carto/external-data.yml",
    ]
    env = dict(__import__("os").environ)
    env["PGPASSWORD"] = cfg.db.password

    # We run this inside /opt/openstreetmap-carto so it finds its data dir
    _run(cmd, env=env, cwd="/opt/openstreetmap-carto")

    # The flex lua script for openstreetmap-carto requires the hstore extension
    _run_psql_command(cfg, "CREATE EXTENSION IF NOT EXISTS hstore;")

    # Also run the one-time SQL scripts that set up functions and common tables
    for sql_file_name in ["functions.sql", "common-values.sql"]:
        sql_file = cfg.carto_style_dir / sql_file_name
        if sql_file.exists():
            log.info("Running one-time SQL script: %s", sql_file_name)
            _run_psql(cfg, sql_file)


def run_full_pipeline(cfg: RenderConfig) -> Path:
    """Run the complete timelapse pipeline end-to-end.

    1. Download data and extract region (if needed)
    2. Generate temporal snapshots
    3. Load external shapefiles
    4. For each snapshot: import → render → watermark
    5. Assemble into video

    """
    # Add file logging
    log_file = cfg.output_video.with_name(f"timelapse_{cfg.cache_key}.log")
    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
    )
    logging.getLogger().addHandler(file_handler)

    log.info("=== OSM Timelapse Pipeline ===")
    log.info("Region: %s", cfg.bbox)
    log.info("Date range: %s to %s (%s)", cfg.start_date, cfg.end_date, cfg.interval)
    log.info("Zoom: %s, Resolution: %dx%d", cfg.zoom or "Auto", cfg.width, cfg.height)
    log.info("Output: %s", cfg.output_video)
    log.info("Log file: %s", log_file)

    # Stage 1: Ensure data is downloaded and region is extracted
    log.info("")
    log.info("--- Stage 1: Ensuring history data is available ---")
    history_file = ensure_data(cfg)
    log.info("Using history file: %s", history_file)

    # Stage 2: Generate snapshots
    log.info("")
    log.info("--- Stage 2: Generating temporal snapshots ---")
    snapshots = generate_all_snapshots(cfg, history_file)
    log.info("Total snapshots: %d", len(snapshots))

    # Stage 3: Load external shapefiles
    log.info("")
    log.info("--- Stage 3: Loading external shapefiles ---")
    setup_external_data(cfg)

    # Stage 4 & 5: Import and render each snapshot
    log.info("")
    log.info("--- Stage 4 & 5: Importing and rendering frames ---")
    cache_key = cfg.cache_key

    # Pre-load Mapnik map to save ~2 seconds of XML parsing per frame
    import mapnik

    width, height = cfg.width, cfg.height
    if (width == 0 or height == 0) and cfg.zoom is not None:
        width, height = compute_pixel_dimensions(cfg.bbox, cfg.zoom)
    
    # Defaults if still 0
    if width == 0: width = 1920
    if height == 0: height = 1080
    log.info("Pre-loading Mapnik XML style...")
    m = mapnik.Map(width, height)
    mapnik.load_map(m, str(cfg.mapnik_xml))

    for i, (d, snapshot_path) in enumerate(snapshots):
        frame_file = cfg.frames_dir / f"frame_{d.isoformat()}_{cache_key}.png"

        # In animation mode, we can skip if the single frame already exists.
        # In tile mode, we enter the loop and let render_tiles handle per-tile caching.
        if cfg.mode == RenderMode.ANIMATION and frame_file.exists():
            log.info("[%d/%d] Frame exists, skipping: %s", i + 1, len(snapshots), d)
            continue

        log.info("[%d/%d] Processing %s ...", i + 1, len(snapshots), d)
        start_time = time.time()

        # Import into PostGIS
        import_snapshot(cfg, snapshot_path)

        if cfg.mode == RenderMode.TILES:
            render_tiles(cfg, m, d)
        else:
            # Render frame
            render_frame(cfg, frame_file, m)

            # Add watermark
            if cfg.watermark:
                label = d.strftime("%B %Y")  # e.g., "January 2015"
                add_watermark(frame_file, label)

        elapsed = time.time() - start_time
        log.info("[%d/%d] Done in %.2fs: %s", i + 1, len(snapshots), elapsed, d)

    # Generate metadata for the web viewer
    if cfg.mode == RenderMode.TILES:
        save_tile_metadata(cfg, snapshots)

    # Stage 6: Assemble video (Animation mode only)
    if cfg.mode == RenderMode.ANIMATION:
        log.info("")
        log.info("--- Stage 6: Assembling video ---")
        video_path = assemble_video(cfg)
        log.info("")
        log.info("=== Pipeline complete! ===")
        log.info("Video: %s", video_path)
        return video_path
    else:
        log.info("")
        log.info("=== Pipeline complete! ===")
        log.info("Tiles generated in: %s", cfg.tiles_dir)
        return cfg.tiles_dir
