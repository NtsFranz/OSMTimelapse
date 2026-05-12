"""Interactive wizard for OSM Timelapse using 'gum'."""

import shutil
import subprocess
import sys
import requests
from datetime import date
from typing import Any, List, Optional, Tuple

from osm_timelapse.dates import generate_dates


def is_gum_available() -> bool:
    """Check if 'gum' is installed on the system."""
    return shutil.which("gum") is not None


def run_gum(command: str, args: List[str]) -> str:
    """Run a gum command and return the result."""
    try:
        result = subprocess.check_output(["gum", command] + args)
        return result.decode("utf-8").strip()
    except subprocess.CalledProcessError:
        # If user cancels (e.g. Ctrl+C), exit gracefully
        sys.exit(0)


def gum_input(header: str, placeholder: str = "", default: str = "") -> str:
    """Get text input using 'gum input'."""
    args = ["--header", header]
    if placeholder:
        args += ["--placeholder", placeholder]
    if default:
        args += ["--value", default]
    return run_gum("input", args)


def gum_choose(options: List[str], header: str) -> str:
    """Select an option using 'gum choose'."""
    return run_gum("choose", ["--header", header] + options)


def gum_confirm(prompt: str) -> bool:
    """Confirm an action using 'gum confirm'."""
    try:
        subprocess.check_call(["gum", "confirm", prompt])
        return True
    except subprocess.CalledProcessError:
        return False


def search_city(name: str) -> Optional[Tuple[float, float, str]]:
    """Search for a city using Nominatim and return (lat, lon, display_name)."""
    url = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": name,
        "format": "json",
        "limit": 1,
        "addressdetails": 1
    }
    headers = {
        "User-Agent": "OSMTimelapse/1.0 (https://github.com/NtsFranz/OSMTimelapse)"
    }
    
    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if not data:
            return None
        
        best = data[0]
        return float(best["lat"]), float(best["lon"]), best["display_name"]
    except Exception as e:
        print(f"Error during geocoding: {e}")
        return None


def interactive_wizard() -> dict:
    """Run the interactive wizard to collect configuration."""
    if not is_gum_available():
        print("Error: 'gum' is not installed. Please install it or use CLI flags.")
        sys.exit(1)

    print("\n  \033[1mOSM Timelapse Wizard\033[0m")
    print("  ──────────────────────\n")

    # 1. Location
    location_mode = gum_choose(
        ["Default (Manhattan)", "Search City by Name", "Custom Bounding Box", "Custom Center + Radius"], 
        "Choose location method:"
    )
    
    config = {}

    if location_mode == "Default (Manhattan)":
        pass  # Use defaults
    elif location_mode == "Search City by Name":
        while True:
            city_query = gum_input("Search City", "e.g. Berlin, New York, Tokyo")
            if not city_query:
                continue
            
            print(f"\nSearching for '{city_query}'...")
            result = search_city(city_query)
            
            if result:
                lat, lon, name = result
                if gum_confirm(f"Found: {name}\nUse this location?"):
                    config["center"] = f"{lat},{lon}"
                    break
            else:
                print(f"No results found for '{city_query}'.")
                if not gum_confirm("Try searching again?"):
                    sys.exit(0)
    elif location_mode == "Custom Bounding Box":
        bbox = gum_input("Bounding Box", "west,south,east,north", "-74.02,40.70,-73.90,40.85")
        config["bbox"] = bbox
    else:
        center = gum_input("Center Point", "lat,lon", "40.758,-73.985")
        radius = gum_input("Radius (km)", "e.g. 2.0", "2.0")
        config["center"] = center
        config["radius"] = float(radius)

    # 2. Dates
    if gum_confirm("Use default date range (2008-01-01 to 2026-01-01)?"):
        pass
    else:
        config["start_date"] = gum_input("Start Date", "YYYY-MM-DD", "2008-01-01")
        config["end_date"] = gum_input("End Date", "YYYY-MM-DD", "2026-01-01")

    # 3. Interval
    intervals = ["daily", "weekly", "monthly", "quarterly", "yearly"]
    options = []
    
    # Parse dates to calculate counts
    from datetime import date
    try:
        s_date = date.fromisoformat(config.get("start_date", "2008-01-01"))
        e_date = date.fromisoformat(config.get("end_date", "2026-01-01"))
    except ValueError:
        s_date, e_date = date(2008, 1, 1), date(2026, 1, 1)

    for interval in intervals:
        count = len(list(generate_dates(s_date, e_date, interval)))
        options.append(f"{interval} ({count} frames)")

    selection = gum_choose(options, "Select time interval:")
    config["interval"] = selection.split(" ")[0]


    # 5. Advanced
    if gum_confirm("Show advanced options?"):
        zoom_raw = gum_input("Map Detail Level (Zoom)", "e.g. 13-18 (leave empty for Auto)", "")
        config["zoom"] = int(zoom_raw) if zoom_raw else None
        config["width"] = int(gum_input("Frame Width", "pixels", "1920"))
        config["height"] = int(gum_input("Frame Height", "pixels", "1080"))
        config["fps"] = int(gum_input("Frames Per Second", "fps", "10"))
        config["no_watermark"] = not gum_confirm("Enable date watermark?")
    else:
        config["zoom"] = None
    
    print("\n  \033[1mReady to start!\033[0m\n")
    return config
