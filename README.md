# OSM Timelapse

Create historical timelapse animations of OpenStreetMap editing progress over time, rendered with the exact standard OSM tile style.

## Quick Start

```bash
# 1. Configure your OpenStreetMap credentials (required for Geofabrik internal data)
cp .env.example .env
# Edit .env and set your OSM_USERNAME and OSM_PASSWORD

# 2. Build and Run!
docker compose up -d --build

# 3. Access the Web Interface
# Open http://localhost:3000 in your browser
```

The web interface allows you to:
- **View existing timelapses** on an interactive map.
- **Generate new timelapses/tiles** by picking coordinates on a map.
- **Browse and download** generated MP4 animations.

That's it. The tool will:
- Download the New York state history file into `./data/` (resumable, cached)
- Extract the Manhattan region into a much smaller file
- Generate ~192 monthly snapshots
- Import and render each one
- Output `./output/timelapse.mp4`

---

## How It Works

```
                          osmium time-filter (per date)
Planet History ──► Region ──► Snapshot ──► PostGIS ──► Mapnik ──► Frame PNG
(auto-download)   Extract     .osm.pbf     Import      Render       │
                                                                    ▼ ffmpeg
                                                              Timelapse Video
```

**Just specify a bounding box** — the tool handles everything else:

1. **Finds** the smallest Geofabrik region containing your bounding box
2. **Authenticates** with OpenStreetMap using your credentials
3. **Downloads** the regional history file (cached for reuse)
4. **Extracts** just your specific bounding box (cached)
5. **Creates snapshots** at each time step via `osmium time-filter`
6. **Imports** each snapshot into PostGIS via `osm2pgsql`
7. **Renders** each frame with the standard OSM style (`openstreetmap-carto` + Mapnik)
8. **Assembles** frames into an MP4 video via `ffmpeg`

## Prerequisites

- **Docker** and **Docker Compose** (v2)
- An **OpenStreetMap Account** (required to download full-history regional data)
- Disk space (a few GB for regional data and frames)

## Custom Regions

```bash
# Specify any bounding box
docker compose run renderer render \
  --bbox "-73.99,40.75,-73.96,40.77" \
  --start-date 2010-01-01 \
  --end-date 2023-01-01 \
  --interval quarterly \
  --zoom 15
```

### Pre-download Data

If you want to download the data separately (e.g., overnight):

```bash
# Download planet history and extract region (can be interrupted and resumed)
docker compose run renderer download --bbox "-74.02,40.70,-73.90,40.85"

# Then render later — it will use the cached data
docker compose run renderer render
```

### Use Your Own History File

If you already have a `.osh.pbf` file (e.g., you downloaded it manually), just drop it in `./data/` and the tool will use it:

```bash
cp my-region.osh.pbf ./data/
docker compose run renderer render --bbox "-74.02,40.70,-73.90,40.85"
```

## CLI Reference

### `osm-timelapse render` (Full Pipeline)

```
Options:
  --bbox TEXT        Bounding box: west,south,east,north [default: Manhattan, NY]
  --start-date TEXT  Start date (YYYY-MM-DD) [default: 2008-01-01]
  --end-date TEXT    End date (YYYY-MM-DD) [default: 2026-01-01]
  --interval CHOICE  daily|weekly|monthly|quarterly|yearly [default: monthly]
  --zoom INT         Map zoom level [default: 13]
  --width INT        Frame width in pixels [default: 1920]
  --height INT       Frame height in pixels [default: 1080]
  --fps INT          Frames per second [default: 10]
  --output PATH      Output video path
  --no-watermark     Disable date label on frames
  --data-dir PATH    Data directory for downloads [default: /data]
```

### Other Commands

```bash
# Download/extract data without rendering
docker compose run renderer download --bbox "west,south,east,north"

# Generate a single snapshot
docker compose run renderer snapshot \
  --input /data/region.osh.pbf \
  --date 2020-06-01 \
  --output /output/snapshot.osm.pbf

# Import a snapshot into PostGIS
docker compose run renderer import --input /output/snapshot.osm.pbf

# Render a single frame from the current DB state
docker compose run renderer render-frame \
  --bbox "-74.02,40.70,-73.90,40.85" \
  --output /output/test_frame.png \
  --label "June 2020"

# Assemble existing frames into a video
docker compose run renderer assemble --fps 10
```

The pipeline is **fully resumable** — every intermediate artifact is cached:

| Artifact | Location | Behavior |
|----------|----------|----------|
| Geofabrik regional history file | `./data/<region>.osh.pbf` | Download resumes if interrupted |
| Bounding box extract | `./data/extract_<hash>.osh.pbf` | Skipped if exists |
| Temporal snapshots | `./output/snapshots/` | Skipped if exists |
| Rendered frames | `./output/frames/` | Skipped if exists |

## Resource Requirements

| Region Size | Date Range | Interval | Approx. Frames | Time Estimate |
|-------------|-----------|----------|----------------|---------------|
| Urban area | 10 years | Monthly | ~120 | 2-6 hours |
| Urban area | 10 years | Yearly | ~10 | 15-30 min |
| City | 10 years | Quarterly | ~40 | 4-12 hours |

**Disk space**: Depends on the Geofabrik region size (e.g., a US state is ~100MB-1GB) plus a few GB for the bounding box extract and frames.

**Bottleneck**: The `osm2pgsql` import — each snapshot requires a full database rebuild.

## Data Sources

| Source | URL | Notes |
|--------|-----|-------|
| Regional history (Geofabrik) | https://osm-internal.download.geofabrik.de/ | Requires OSM account. Automatically used by this tool. |

## Project Structure

```
OSMTimelapse/
├── docker-compose.yml           # PostGIS + renderer (all bind mounts)
├── Dockerfile                   # Renderer with all tools
├── pyproject.toml               # Python project (uv)
├── src/osm_timelapse/
│   ├── cli.py                   # Click CLI
│   ├── config.py                # Configuration (defaults to Manhattan, NY)
│   ├── dates.py                 # Date range generation
│   ├── downloader.py            # Auto-download & region extraction
│   ├── pipeline.py              # Core pipeline orchestration
│   └── tile_math.py             # Coordinate conversions
├── data/                        # Downloaded history files (bind mount, gitignored)
├── output/                      # Frames + video (bind mount, gitignored)
└── pgdata/                      # PostgreSQL data (bind mount, gitignored)
```

## License

MIT
