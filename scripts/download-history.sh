#!/usr/bin/env bash
# =============================================================================
# Download a full-history OSM extract
#
# Usage:
#   ./scripts/download-history.sh [URL] [OUTPUT_DIR]
#
# Examples:
#   # Download the full planet history (WARNING: ~130GB)
#   ./scripts/download-history.sh
#
#   # Download to a specific directory
#   ./scripts/download-history.sh https://planet.openstreetmap.org/pbf/full-history/history-latest.osm.pbf ./data
# =============================================================================

set -euo pipefail

DEFAULT_URL="https://planet.openstreetmap.org/pbf/full-history/history-latest.osm.pbf"
URL="${1:-$DEFAULT_URL}"
OUTPUT_DIR="${2:-./data}"

mkdir -p "$OUTPUT_DIR"

FILENAME=$(basename "$URL")
OUTPUT_PATH="$OUTPUT_DIR/$FILENAME"

echo "============================================="
echo "OSM Full History Download"
echo "============================================="
echo "URL:    $URL"
echo "Output: $OUTPUT_PATH"
echo ""
echo "WARNING: The full planet history file is ~130GB."
echo "         Consider using a regional extract instead."
echo "         See: https://download.geofabrik.de/"
echo ""
echo "For regional history extracts (requires OSM account):"
echo "  https://osm-internal.download.geofabrik.de/"
echo "============================================="
echo ""

# Use wget with resume support
if command -v wget &> /dev/null; then
    echo "Downloading with wget (resume-capable)..."
    wget --continue --progress=bar:force "$URL" -O "$OUTPUT_PATH"
elif command -v curl &> /dev/null; then
    echo "Downloading with curl (resume-capable)..."
    curl -L -C - -o "$OUTPUT_PATH" "$URL"
else
    echo "ERROR: Neither wget nor curl found. Please install one of them."
    exit 1
fi

echo ""
echo "Download complete: $OUTPUT_PATH"
echo "File size: $(du -h "$OUTPUT_PATH" | cut -f1)"
