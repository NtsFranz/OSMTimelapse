# OSM Timelapse

Create historical timelapse animations of OpenStreetMap editing progress over time, rendered with the exact standard OSM tile style.

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

## Quick Start

```bash
# 1. Export your OpenStreetMap credentials (required for Geofabrik internal data)
export OSM_USERNAME="your_username"
export OSM_PASSWORD="your_password"

# 2. Clone and build
git clone <repo-url>
cd OSMTimelapse
docker compose build

# 3. Run! (defaults to Watkinsville, GA — monthly from 2008 to 2024)
docker compose run renderer render
```

That's it. The tool will:
- Download the Georgia state history file into `./data/` (resumable, cached)
- Extract the Watkinsville region into a much smaller file
- Generate ~192 monthly snapshots
- Import and render each one
- Output `./output/timelapse.mp4`

### Custom Region

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
docker compose run renderer download --bbox "-83.45,33.83,-83.37,33.90"

# Then render later — it will use the cached data
docker compose run renderer render
```

### Use Your Own History File

If you already have a `.osh.pbf` file (e.g., you downloaded it manually), just drop it in `./data/` and the tool will use it:

```bash
cp my-region.osh.pbf ./data/
docker compose run renderer render --bbox "-83.45,33.83,-83.37,33.90"
```

## CLI Reference

### `osm-timelapse render` (Full Pipeline)

```
Options:
  --bbox TEXT        Bounding box: west,south,east,north [default: Watkinsville, GA]
  --start-date TEXT  Start date (YYYY-MM-DD) [default: 2008-01-01]
  --end-date TEXT    End date (YYYY-MM-DD) [default: 2024-01-01]
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
  --bbox "-83.45,33.83,-83.37,33.90" \
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

If a run is interrupted, just re-run the same command.

## Resource Requirements

| Region Size | Date Range | Interval | Approx. Frames | Time Estimate |
|-------------|-----------|----------|----------------|---------------|
| Small town | 10 years | Monthly | ~120 | 2-6 hours |
| Small town | 10 years | Yearly | ~10 | 15-30 min |
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
│   ├── config.py                # Configuration (defaults to Watkinsville, GA)
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
