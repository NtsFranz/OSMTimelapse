<script lang="ts">
    import { onMount, untrack } from 'svelte';
    import maplibregl from 'maplibre-gl';
    import 'maplibre-gl/dist/maplibre-gl.css';

    let map = $state<maplibregl.Map | null>(null);
    let dates = $state<string[]>([]);
    let currentIndex = $state(0);
    let center = $state([33.8824, -83.4351]);
    let zoom = $state(15);
    let loading = $state(true);
    let isLoaded = $state(false);
    let showBaseLayer = $state(false);
    let isPlaying = $state(false);
    let currentLayerId = '';
    let pendingLayerId = '';

    $effect(() => {
        let interval: ReturnType<typeof setInterval>;
        if (isPlaying) {
            interval = setInterval(() => {
                if (currentIndex < dates.length - 1) {
                    currentIndex++;
                } else {
                    currentIndex = 0;
                }
            }, 200);
        }
        return () => clearInterval(interval);
    });

    let yearTicks = $derived.by(() => {
        const ticks: { year: number, percent: number }[] = [];
        let lastYear = -1;
        dates.forEach((d, i) => {
            const year = new Date(d).getUTCFullYear();
            if (year !== lastYear) {
                const percent = (i / (dates.length - 1)) * 100;
                ticks.push({ year, percent });
                lastYear = year;
            }
        });
        return ticks;
    });

    async function generateMonthlyDates(startStr: string, endStr: string) {
        const result = [];
        let current = new Date(startStr);
        const end = new Date(endStr);
        current.setUTCDate(1);
        while (current <= end) {
            result.push(current.toISOString().split('T')[0]);
            current.setUTCMonth(current.getUTCMonth() + 1);
        }
        return result;
    }

    function formatDate(dateStr: string) {
        const d = new Date(dateStr);
        return d.toLocaleDateString('en-US', { month: 'long', year: 'numeric', timeZone: 'UTC' }).toUpperCase();
    }

    function getTileUrl(date: string) {
        // Use the SvelteKit proxy route
        return `/tiles/${date}/{z}/{x}/{y}.png`;
    }

    onMount(async () => {
        try {
            const response = await fetch('/metadata.json');
            if (response.ok) {
                const metadata = await response.json();
                dates = metadata.dates;
                center = metadata.center;
                zoom = metadata.default_zoom || 15;
            } else {
                throw new Error();
            }
        } catch (err) {
            console.warn("Metadata not found, falling back to defaults.");
            const params = new URLSearchParams(window.location.search);
            const start = params.get('start') || '2020-01-01';
            const end = params.get('end') || new Date().toISOString().split('T')[0];
            const lat = parseFloat(params.get('lat') || '33.8824');
            const lon = parseFloat(params.get('lon') || '-83.4351');
            center = [lat, lon];
            zoom = parseInt(params.get('zoom') || '15');
            dates = await generateMonthlyDates(start, end);
        }

        currentIndex = dates.length - 1;
        loading = false;

        map = new maplibregl.Map({
            container: 'map',
            style: {
                version: 8,
                sources: {
                    'osm': {
                        type: 'raster',
                        tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
                        tileSize: 256,
                        attribution: '&copy; OpenStreetMap contributors'
                    },
                },
                layers: [
                    {
                        id: 'osm-layer',
                        type: 'raster',
                        source: 'osm',
                        paint: { 
                            'raster-opacity': 0.3,
                            'raster-fade-duration': 0
                        },
                        layout: {
                            visibility: 'none'
                        }
                    }
                ]
            },
            center: [center[1], center[0]],
            zoom: zoom
        });

        map.on('load', () => {
            isLoaded = true;
        });

        // Cleanup on unmount
        return () => {
            if (map) map.remove();
        };
    });

    // Reactively update the map when currentIndex or base layer toggle changes
    $effect(() => {
        const date = dates[currentIndex];
        const show = showBaseLayer;

        untrack(() => {
            if (!map || !isLoaded || !date) return;
            
            const newLayerId = `hist-${date}`;
            const newSourceId = `src-${date}`;

            // If it's already the current layer, just update OSM visibility
            if (newLayerId === currentLayerId) {
                map.setLayoutProperty('osm-layer', 'visibility', show ? 'visible' : 'none');
                return;
            }

            // If we are already trying to load this specific layer, just wait
            if (newLayerId === pendingLayerId) return;

            // Remove any other pending layer that didn't finish loading
            if (pendingLayerId && map.getLayer(pendingLayerId)) {
                map.removeLayer(pendingLayerId);
                map.removeSource(pendingLayerId.replace('hist-', 'src-'));
            }

            pendingLayerId = newLayerId;

            try {
                map.addSource(newSourceId, {
                    type: 'raster',
                    tiles: [getTileUrl(date)],
                    tileSize: 256
                });

                map.addLayer({
                    id: newLayerId,
                    type: 'raster',
                    source: newSourceId,
                    paint: { 'raster-fade-duration': 0 }
                });

                // Poll for loading
                let attempts = 0;
                const checkAndSwap = () => {
                    if (!map || pendingLayerId !== newLayerId) return;

                    if (map.isSourceLoaded(newSourceId) || attempts > 50) {
                        // Swap!
                        if (currentLayerId && map.getLayer(currentLayerId)) {
                            map.removeLayer(currentLayerId);
                            map.removeSource(currentLayerId.replace('hist-', 'src-'));
                        }
                        currentLayerId = newLayerId;
                        pendingLayerId = '';
                        map.setLayoutProperty('osm-layer', 'visibility', show ? 'visible' : 'none');
                    } else {
                        attempts++;
                        requestAnimationFrame(checkAndSwap);
                    }
                };
                requestAnimationFrame(checkAndSwap);
            } catch (e) {
                console.warn("Layer swap failed:", e);
                pendingLayerId = '';
            }
        });
    });
</script>

<div id="map"></div>

{#if !loading}
    <div class="controls">
        <div class="info">
            <div class="date-display">
                <button 
                    class="play-button" 
                    onclick={() => isPlaying = !isPlaying}
                    aria-label={isPlaying ? 'Pause' : 'Play'}
                >
                    {#if isPlaying}
                        <svg viewBox="0 0 24 24" fill="currentColor"><path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/></svg>
                    {:else}
                        <svg viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>
                    {/if}
                </button>
                <div>
                    <p>HISTORICAL TIMELINE</p>
                    <h1>{formatDate(dates[currentIndex])}</h1>
                </div>
            </div>
            <p>LAT: {center[0].toFixed(4)} LON: {center[1].toFixed(4)}</p>
        </div>
        <div class="options">
            <label>
                <input type="checkbox" bind:checked={showBaseLayer}> 
                Show Modern OSM Base Map
            </label>
        </div>
        <div class="slider-container">
            <input 
                type="range" 
                min="0" 
                max={dates.length - 1} 
                bind:value={currentIndex}
            >
            <div class="ticks">
                {#each yearTicks as tick (tick.year)}
                    <div class="tick" style:left="{tick.percent}%">
                        <span class="tick-label">{tick.year}</span>
                    </div>
                {/each}
            </div>
        </div>
    </div>
{/if}

<style>
    .options {
        display: flex;
        gap: 20px;
        font-size: 14px;
        opacity: 0.9;
    }
    .options label {
        display: flex;
        align-items: center;
        gap: 8px;
        cursor: pointer;
        user-select: none;
    }
    .options input[type=checkbox] {
        width: 16px;
        height: 16px;
        cursor: pointer;
        accent-color: #38bdf8;
    }
    :global(body, html) {
        margin: 0;
        padding: 0;
        height: 100%;
        width: 100%;
        font-family: 'Inter', -apple-system, sans-serif;
        background: #0f172a;
        color: #f8fafc;
        overflow: hidden;
    }

    #map {
        position: absolute;
        top: 0;
        bottom: 0;
        width: 100%;
        background: #0f172a;
    }

    .controls {
        position: absolute;
        bottom: 30px;
        left: 50%;
        transform: translateX(-50%);
        width: 90%;
        max-width: 800px;
        background: rgba(30, 41, 59, 0.8);
        backdrop-filter: blur(12px);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 20px;
        padding: 20px 30px;
        box-shadow: 0 10px 25px rgba(0, 0, 0, 0.5);
        display: flex;
        flex-direction: column;
        gap: 15px;
        z-index: 1000;
    }

    .info {
        display: flex;
        justify-content: space-between;
        align-items: flex-end;
    }

    .date-display {
        display: flex;
        align-items: center;
        gap: 20px;
    }

    .play-button {
        background: var(--accent-color, #38bdf8);
        border: none;
        color: #0f172a;
        width: 48px;
        height: 48px;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        cursor: pointer;
        transition: all 0.2s ease;
        box-shadow: 0 4px 12px rgba(56, 189, 248, 0.3);
    }

    .play-button:hover {
        transform: scale(1.1);
        box-shadow: 0 6px 16px rgba(56, 189, 248, 0.4);
    }

    .play-button svg {
        width: 24px;
        height: 24px;
    }

    h1 {
        margin: 0;
        font-size: 24px;
        font-weight: 700;
        color: #38bdf8;
        text-shadow: 0 2px 4px rgba(0,0,0,0.3);
    }

    p {
        margin: 0;
        font-size: 14px;
        opacity: 0.8;
        font-family: monospace;
    }

    .slider-container {
        width: 100%;
    }

    input[type=range] {
        -webkit-appearance: none;
        width: 100%;
        background: transparent;
    }

    input[type=range]:focus {
        outline: none;
    }

    input[type=range]::-webkit-slider-runnable-track {
        width: 100%;
        height: 6px;
        cursor: pointer;
        background: rgba(255, 255, 255, 0.3);
        border-radius: 3px;
    }

    input[type=range]::-moz-range-track {
        width: 100%;
        height: 6px;
        cursor: pointer;
        background: rgba(255, 255, 255, 0.3);
        border-radius: 3px;
    }

    input[type=range]::-webkit-slider-thumb {
        height: 24px;
        width: 24px;
        border-radius: 50%;
        background: #38bdf8;
        cursor: pointer;
        -webkit-appearance: none;
        margin-top: -9px;
        box-shadow: 0 0 10px rgba(56, 189, 248, 0.5);
        transition: transform 0.1s ease;
        z-index: 2;
        position: relative;
    }

    .ticks {
        position: relative;
        width: 100%;
        height: 20px;
        margin-top: 10px;
    }

    .tick {
        position: absolute;
        width: 1px;
        height: 6px;
        background: rgba(255, 255, 255, 0.4);
        top: -14px;
    }

    .tick-label {
        position: absolute;
        top: 10px;
        transform: translateX(-50%);
        font-size: 10px;
        font-weight: 600;
        opacity: 0.6;
        letter-spacing: 0.05em;
    }

    input[type=range]:active::-webkit-slider-thumb {
        transform: scale(1.2);
    }
</style>
