"""CLI entry point for OSM Timelapse."""

from __future__ import annotations

import logging
import sys
from datetime import date
from pathlib import Path

import click

from osm_timelapse.config import BBox, RenderConfig


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stderr,
    )


def _parse_center(ctx, param, value: str | None) -> tuple[float, float]:
    from osm_timelapse.config import DEFAULT_CENTER
    if value is None:
        return DEFAULT_CENTER
    parts = [float(x.strip()) for x in value.split(",")]
    if len(parts) != 2:
        raise ValueError(f"Expected lat,lon string, got {len(parts)} values")
    return (parts[0], parts[1])


def _parse_date(ctx, param, value: str | None) -> date | None:
    if value is None:
        return None
    return date.fromisoformat(value)


@click.group()
@click.option("-v", "--verbose", is_flag=True, help="Enable debug logging.")
@click.pass_context
def cli(ctx: click.Context, verbose: bool) -> None:
    """OSM Timelapse — Create historical timelapse renders of OpenStreetMap data."""
    _setup_logging(verbose)
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose


@cli.command()
@click.option(
    "--center",
    callback=_parse_center,
    default=None,
    help="Center point: lat,lon. Default: Watkinsville, GA.",
)
@click.option(
    "--radius",
    type=float,
    default=2.0,
    help="Radius around center point in kilometers. Default: 2.0.",
)
@click.option(
    "--start-date",
    callback=_parse_date,
    default="2008-01-01",
    help="Start date (YYYY-MM-DD).",
)
@click.option(
    "--end-date",
    callback=_parse_date,
    default="2024-01-01",
    help="End date (YYYY-MM-DD).",
)
@click.option(
    "--interval",
    type=click.Choice(["daily", "weekly", "monthly", "quarterly", "yearly"]),
    default="monthly",
    help="Time step interval.",
)
@click.option("--zoom", type=int, default=13, help="Map zoom level.")
@click.option("--width", type=int, default=1920, help="Frame width in pixels.")
@click.option("--height", type=int, default=1080, help="Frame height in pixels.")
@click.option("--fps", type=int, default=10, help="Frames per second in output video.")
@click.option("--output", type=click.Path(), default=None, help="Output video path. If not provided, defaults to /output/timelapse_[params].mp4")
@click.option("--no-watermark", is_flag=True, help="Disable date watermark on frames.")
@click.option("--data-dir", type=click.Path(), default="/data", help="Data directory for downloads and cache.")
def render(
    center: tuple[float, float],
    radius: float,
    start_date: date,
    end_date: date,
    interval: str,
    zoom: int,
    width: int,
    height: int,
    fps: int,
    output: str | None,
    no_watermark: bool,
    data_dir: str,
) -> None:
    """Run the full timelapse pipeline.

    Downloads OSM history data automatically, extracts temporal snapshots,
    imports each into PostGIS, renders with the standard OSM style, and
    assembles the frames into a timelapse video.

    Just specify a --bbox and the tool handles everything else.
    """
    from osm_timelapse.pipeline import run_full_pipeline

    cfg = RenderConfig(
        data_dir=Path(data_dir),
        center=center,
        radius_km=radius,
        start_date=start_date,
        end_date=end_date,
        interval=interval,
        zoom=zoom,
        width=width,
        height=height,
        fps=fps,
        watermark=not no_watermark,
    )
    if output is None:
        cfg.output_video = Path(f"/output/timelapse_{cfg.cache_key}.mp4")
    else:
        cfg.output_video = Path(output)

    run_full_pipeline(cfg)


@cli.command("download")
@click.option(
    "--center",
    callback=_parse_center,
    default=None,
    help="Center point: lat,lon.",
)
@click.option("--radius", type=float, default=2.0, help="Radius around center in km.")
@click.option("--data-dir", type=click.Path(), default="/data", help="Data directory.")
def download_cmd(center: tuple[float, float], radius: float, data_dir: str) -> None:
    """Download OSM history data and extract the region.

    Downloads the full planet history file (if not cached) and extracts
    just the bounding box region with history data.
    """
    from osm_timelapse.downloader import ensure_history_data

    result = ensure_history_data(
        data_dir=Path(data_dir),
        bbox=BBox.from_center(center[0], center[1], radius).to_osmium_arg(),
    )
    click.echo(f"History data ready: {result}")


@cli.command("snapshot")
@click.option(
    "--input", "input_file",
    type=click.Path(exists=True),
    required=True,
    help="Path to history .osh.pbf file.",
)
@click.option(
    "--date", "target_date",
    callback=_parse_date,
    required=True,
    help="Date to extract snapshot for (YYYY-MM-DD).",
)
@click.option(
    "--output", "output_file",
    type=click.Path(),
    required=True,
    help="Output .osm.pbf path.",
)
def snapshot_cmd(input_file: str, target_date: date, output_file: str) -> None:
    """Generate a single point-in-time snapshot."""
    from osm_timelapse.pipeline import generate_snapshot

    result = generate_snapshot(Path(input_file), target_date, Path(output_file))
    click.echo(f"Snapshot written to: {result}")


@cli.command("import")
@click.option(
    "--input", "input_file",
    type=click.Path(exists=True),
    required=True,
    help="Path to .osm.pbf snapshot file.",
)
def import_cmd(input_file: str) -> None:
    """Import a .osm.pbf file into PostGIS."""
    from osm_timelapse.pipeline import import_snapshot

    cfg = RenderConfig()
    import_snapshot(cfg, Path(input_file))
    click.echo("Import complete.")


@cli.command("render-frame")
@click.option("--center", callback=_parse_center, default=None, help="Center point: lat,lon.")
@click.option("--radius", type=float, default=2.0, help="Radius in km.")
@click.option("--zoom", type=int, default=13, help="Zoom level.")
@click.option("--width", type=int, default=1920, help="Frame width.")
@click.option("--height", type=int, default=1080, help="Frame height.")
@click.option("--output", type=click.Path(), required=True, help="Output PNG path.")
@click.option("--label", type=str, default=None, help="Watermark text.")
def render_frame_cmd(
    center: tuple[float, float],
    radius: float,
    zoom: int,
    width: int,
    height: int,
    output: str,
    label: str | None,
) -> None:
    """Render a single frame from the current PostGIS database state."""
    from osm_timelapse.pipeline import add_watermark, render_frame

    cfg = RenderConfig(center=center, radius_km=radius, zoom=zoom, width=width, height=height)
    render_frame(cfg, Path(output))
    if label:
        add_watermark(Path(output), label)
    click.echo(f"Frame rendered: {output}")


@cli.command("assemble")
@click.option(
    "--frames-dir",
    type=click.Path(exists=True),
    default="/output/frames",
    help="Directory containing frame PNGs.",
)
@click.option("--fps", type=int, default=10, help="Frames per second.")
@click.option("--output", type=click.Path(), default="/output/timelapse.mp4", help="Output video path.")
def assemble_cmd(frames_dir: str, fps: int, output: str) -> None:
    """Assemble rendered frames into a timelapse video."""
    from osm_timelapse.pipeline import assemble_video

    cfg = RenderConfig(
        fps=fps,
        output_video=Path(output),
    )
    # Override frames_dir
    cfg.frames_dir = Path(frames_dir)
    assemble_video(cfg)
    click.echo(f"Video created: {output}")


if __name__ == "__main__":
    cli()
