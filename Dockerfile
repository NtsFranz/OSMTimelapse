# =============================================================================
# OSM Timelapse — Renderer Container
#
# Contains: osmium-tool, osm2pgsql, Mapnik + python3-mapnik,
#           openstreetmap-carto (compiled), carto (Node.js), ffmpeg, Python/uv
# =============================================================================

FROM debian:bookworm-slim AS base

ENV DEBIAN_FRONTEND=noninteractive
ENV LANG=C.UTF-8

# ---------------------------------------------------------------------------
# System dependencies
# ---------------------------------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Build essentials
    ca-certificates curl wget git unzip \
    # PostgreSQL client (for psql)
    postgresql-client \
    # osmium
    osmium-tool \
    # osm2pgsql
    osm2pgsql \
    # Mapnik + Python bindings
    libmapnik-dev mapnik-utils python3-mapnik \
    # Python
    python3 python3-pip python3-venv python3-dev python3-pil \
    python3-yaml python3-psycopg2 python3-requests \
    # Node.js (for carto compiler)
    nodejs npm \
    # FFmpeg
    ffmpeg \
    # Fonts used by openstreetmap-carto
    fonts-dejavu fonts-hanazono fonts-noto-cjk fonts-noto-cjk-extra \
    fonts-noto-hinted fonts-noto-unhinted \
    # Shape file tools
    gdal-bin \
    && rm -rf /var/lib/apt/lists/*

# ---------------------------------------------------------------------------
# Install carto (CartoCSS → Mapnik XML compiler)
# ---------------------------------------------------------------------------
RUN npm install -g carto

# ---------------------------------------------------------------------------
# Clone and set up openstreetmap-carto
# ---------------------------------------------------------------------------
WORKDIR /opt
RUN git clone --depth 1 https://github.com/gravitystorm/openstreetmap-carto.git

WORKDIR /opt/openstreetmap-carto

# Download required shapefiles
RUN python3 scripts/get-external-data.py || \
    (scripts/get-external-data.py 2>/dev/null || \
     echo "Shapefile download may need manual setup — continuing build")

# Compile CartoCSS to Mapnik XML
RUN carto project.mml > mapnik.xml

# ---------------------------------------------------------------------------
# Install uv and set up the Python project
# ---------------------------------------------------------------------------
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml .python-version README.md ./
COPY src/ ./src/

# Install the project
RUN uv venv --python /usr/bin/python3 --system-site-packages && uv sync --no-dev

# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------
# Make the CLI available via uv run
ENTRYPOINT ["uv", "run", "osm-timelapse"]
CMD ["--help"]
