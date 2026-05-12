<script lang="ts">
	import { onMount } from 'svelte';
	import maplibregl from 'maplibre-gl';
	import 'maplibre-gl/dist/maplibre-gl.css';
	import { resolve } from '$app/paths';

	let map = $state<maplibregl.Map | null>(null);
	let isLoaded = $state(false);
	let lat = $state(40.758);
	let lon = $state(-73.985);
	let radius = $state(2.0);
	let interval = $state('monthly');
	let startDate = $state('2020-01-01');
	let endDate = $state(new Date().toISOString().split('T')[0]);
	let mode = $state('animation'); // 'animation' or 'tiles'
	let selectedZooms = $state<number[]>([13, 14, 15, 16]);
	const availableZooms = [10, 11, 12, 13, 14, 15, 16, 17, 18];
	let isSubmitting = $state(false);
	let message = $state('');
	let activeJobId = $state<string | null>(null);
	let jobStatus = $state<{
		status: string;
		progress: number;
		totalSteps: number;
		currentStepText: string;
		percent: number;
		lastLine: string;
	} | null>(null);

	$effect(() => {
		let interval: ReturnType<typeof setInterval>;
		if (
			activeJobId &&
			(!jobStatus || (jobStatus.status !== 'finished' && jobStatus.status !== 'error'))
		) {
			interval = setInterval(async () => {
				try {
					const response = await fetch(`/api/status/${activeJobId}`);
					if (response.ok) {
						jobStatus = await response.json();
					}
				} catch {
					console.error('Failed to poll status');
				}
			}, 1000);
		}
		return () => clearInterval(interval);
	});

	function calculateFrames(iv: string) {
		const start = new Date(startDate);
		const end = new Date(endDate);
		if (isNaN(start.getTime()) || isNaN(end.getTime()) || start > end) return 0;

		const diffMs = end.getTime() - start.getTime();
		const diffDays = diffMs / (1000 * 60 * 60 * 24);

		if (iv === 'daily') return Math.floor(diffDays) + 1;
		if (iv === 'weekly') return Math.floor(diffDays / 7) + 1;
		if (iv === 'monthly') {
			return (
				(end.getFullYear() - start.getFullYear()) * 12 + (end.getMonth() - start.getMonth()) + 1
			);
		}
		if (iv === 'quarterly') {
			return (
				Math.floor(
					((end.getFullYear() - start.getFullYear()) * 12 + (end.getMonth() - start.getMonth())) / 3
				) + 1
			);
		}
		if (iv === 'yearly') return end.getFullYear() - start.getFullYear() + 1;
		return 0;
	}

	let estimatedFrames = $derived(calculateFrames(interval));

	// Load from localStorage on mount
	onMount(() => {
		const saved = localStorage.getItem('generator_settings');
		if (saved) {
			try {
				const settings = JSON.parse(saved);
				lat = settings.lat ?? lat;
				lon = settings.lon ?? lon;
				radius = settings.radius ?? radius;
				interval = settings.interval ?? interval;
				startDate = settings.startDate ?? startDate;
				endDate = settings.endDate ?? endDate;
				mode = settings.mode ?? mode;
				selectedZooms = settings.selectedZooms ?? selectedZooms;
			} catch {
				console.error('Failed to parse saved settings');
			}
		}

		map = new maplibregl.Map({
			container: 'map-picker',
			style: {
				version: 8,
				sources: {
					osm: {
						type: 'raster',
						tiles: ['https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png'],
						tileSize: 256,
						attribution: '&copy; OpenStreetMap contributors &copy; CARTO'
					}
				},
				layers: [
					{
						id: 'osm',
						type: 'raster',
						source: 'osm'
					}
				]
			},
			center: [lon, lat],
			zoom: 13
		});

		const marker = new maplibregl.Marker({ draggable: true }).setLngLat([lon, lat]).addTo(map);

		marker.on('dragend', () => {
			const lngLat = marker.getLngLat();
			lon = lngLat.lng;
			lat = lngLat.lat;
		});

		map.on('click', (e) => {
			marker.setLngLat(e.lngLat);
			lon = e.lngLat.lng;
			lat = e.lngLat.lat;
		});

		map.on('load', () => {
			isLoaded = true;
			map?.addSource('bounds', {
				type: 'geojson',
				data: { type: 'FeatureCollection', features: [] }
			});

			map?.addLayer({
				id: 'bounds-line',
				type: 'line',
				source: 'bounds',
				paint: {
					'line-color': '#38bdf8',
					'line-width': 2,
					'line-dasharray': [2, 2]
				}
			});

			map?.addLayer({
				id: 'bounds-fill',
				type: 'fill',
				source: 'bounds',
				paint: {
					'fill-color': '#38bdf8',
					'fill-opacity': 0.1
				}
			});
		});

		return () => map?.remove();
	});

	$effect(() => {
		if (!map || !isLoaded) return;
		const source = map.getSource('bounds') as maplibregl.GeoJSONSource;
		if (!source) return;

		// Calculate approximate bounding box matching CLI logic
		// 1 degree lat ~ 111km
		let dLat = radius / 111;
		let dLon = radius / (111 * Math.cos(lat * (Math.PI / 180)));

		// Adjust for 16:9 aspect ratio (1920x1080)
		const aspect = 1920 / 1080;
		if (aspect > 1.0) {
			dLon *= aspect;
		} else {
			dLat /= aspect;
		}

		const west = lon - dLon;
		const east = lon + dLon;
		const south = lat - dLat;
		const north = lat + dLat;

		const geojson: GeoJSON.FeatureCollection = {
			type: 'FeatureCollection',
			features: [
				{
					type: 'Feature',
					geometry: {
						type: 'Polygon',
						coordinates: [
							[
								[west, north],
								[east, north],
								[east, south],
								[west, south],
								[west, north]
							]
						]
					},
					properties: {}
				}
			]
		};

		(map.getSource('bounds') as maplibregl.GeoJSONSource).setData(geojson);
	});

	// Save to localStorage when settings change
	$effect(() => {
		const settings = { lat, lon, radius, interval, startDate, endDate, mode, selectedZooms };
		localStorage.setItem('generator_settings', JSON.stringify(settings));
	});

	async function handleSubmit() {
		isSubmitting = true;
		message = 'Starting generation process...';
		jobStatus = null;
		activeJobId = null;

		try {
			const response = await fetch('/api/render', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({
					lat,
					lon,
					radius,
					interval,
					startDate,
					endDate,
					mode,
					tileZooms: mode === 'tiles' ? selectedZooms : []
				})
			});

			const data = await response.json();
			if (response.ok) {
				message = '';
				activeJobId = data.jobId;
			} else {
				message = `Error: ${data.error}`;
			}
		} catch {
			message = 'Failed to trigger rendering.';
		} finally {
			isSubmitting = false;
		}
	}
</script>

<div class="flex h-[calc(100vh-3.5rem)] bg-slate-950 text-white">
	<!-- Left: Form -->
	<div class="w-1/3 overflow-y-auto border-r border-white/10 p-8">
		<h2 class="mb-6 text-2xl font-bold text-sky-400">Generate New Timelapse</h2>

		<form onsubmit={handleSubmit} class="space-y-6">
			<div>
				<label for="lat" class="mb-1 block text-sm font-medium text-slate-400"
					>Location (Center)</label
				>
				<div class="grid grid-cols-2 gap-4">
					<input
						id="lat"
						type="number"
						step="any"
						bind:value={lat}
						class="rounded-lg border border-white/10 bg-slate-900 p-2 text-white"
						placeholder="Latitude"
					/>
					<input
						id="lon"
						type="number"
						step="any"
						bind:value={lon}
						class="rounded-lg border border-white/10 bg-slate-900 p-2 text-white"
						placeholder="Longitude"
						aria-label="Longitude"
					/>
				</div>
				<p class="mt-1 text-xs text-slate-500">Drag the marker on the map to select center.</p>
			</div>

			<div>
				<label for="radius" class="mb-1 block text-sm font-medium text-slate-400">Radius (km)</label
				>
				<input
					id="radius"
					type="number"
					step="0.1"
					bind:value={radius}
					class="w-full rounded-lg border border-white/10 bg-slate-900 p-2 text-white"
				/>
			</div>

			<div class="grid grid-cols-2 gap-4">
				<div>
					<label for="start-date" class="mb-1 block text-sm font-medium text-slate-400"
						>Start Date</label
					>
					<input
						id="start-date"
						type="date"
						bind:value={startDate}
						class="w-full rounded-lg border border-white/10 bg-slate-900 p-2 text-white"
					/>
				</div>
				<div>
					<label for="end-date" class="mb-1 block text-sm font-medium text-slate-400"
						>End Date</label
					>
					<input
						id="end-date"
						type="date"
						bind:value={endDate}
						class="w-full rounded-lg border border-white/10 bg-slate-900 p-2 text-white"
					/>
				</div>
			</div>

			<div>
				<div class="mb-1 flex items-center justify-between">
					<label for="interval" class="text-sm font-medium text-slate-400">Interval</label>
					<span class="text-xs font-bold text-sky-400/80">Est. {estimatedFrames} frames</span>
				</div>
				<select
					id="interval"
					bind:value={interval}
					class="w-full rounded-lg border border-white/10 bg-slate-900 p-2 text-white"
				>
					<option value="daily">Daily ({calculateFrames('daily')} frames)</option>
					<option value="weekly">Weekly ({calculateFrames('weekly')} frames)</option>
					<option value="monthly">Monthly ({calculateFrames('monthly')} frames)</option>
					<option value="quarterly">Quarterly ({calculateFrames('quarterly')} frames)</option>
					<option value="yearly">Yearly ({calculateFrames('yearly')} frames)</option>
				</select>
			</div>

			<div>
				<p class="mb-2 block text-sm font-medium text-slate-400">Output Mode</p>
				<div class="flex gap-4">
					<label class="flex cursor-pointer items-center gap-2">
						<input type="radio" value="animation" bind:group={mode} class="accent-sky-500" />
						Animation (MP4)
					</label>
					<label class="flex cursor-pointer items-center gap-2">
						<input type="radio" value="tiles" bind:group={mode} class="accent-sky-500" />
						Map Tiles (Viewer)
					</label>
				</div>
			</div>

			{#if mode === 'tiles'}
				<div class="animate-in fade-in slide-in-from-top-2 duration-300">
					<p class="mb-2 block text-sm font-medium text-slate-400">Zoom Levels</p>
					<div class="flex flex-wrap gap-2">
						{#each availableZooms as z (z)}
							<label
								class="flex h-10 w-10 cursor-pointer items-center justify-center rounded-lg border border-white/10 bg-slate-900 transition-all hover:border-sky-500/50 {selectedZooms.includes(
									z
								)
									? 'border-sky-500 bg-sky-500/10 text-sky-400'
									: ''}"
							>
								<input
									type="checkbox"
									checked={selectedZooms.includes(z)}
									onchange={(e) => {
										if (e.currentTarget.checked) {
											if (!selectedZooms.includes(z)) {
												selectedZooms.push(z);
												selectedZooms.sort((a, b) => a - b);
											}
										} else {
											selectedZooms = selectedZooms.filter((x) => x !== z);
										}
									}}
									class="hidden"
								/>
								<span class="text-sm font-bold">{z}</span>
							</label>
						{/each}
					</div>
					<p class="mt-2 text-xs text-slate-500">
						Higher zooms (17-18) take significantly longer to render.
					</p>
				</div>
			{/if}

			<button
				type="submit"
				disabled={isSubmitting}
				class="w-full rounded-xl bg-sky-500 py-3 font-bold text-slate-950 transition-all hover:bg-sky-400 disabled:opacity-50"
			>
				{isSubmitting ? 'Starting...' : 'Launch Generation Pipeline'}
			</button>
		</form>

		{#if message}
			<div class="mt-6 rounded-lg border border-sky-500/30 bg-slate-900 p-4 text-sm text-sky-200">
				{message}
			</div>
		{/if}

		{#if activeJobId && jobStatus}
			<div
				class="mt-8 space-y-4 rounded-2xl border border-white/10 bg-slate-900/50 p-6 backdrop-blur-md"
			>
				<div class="flex justify-between text-sm font-bold">
					<span class="text-sky-400">
						{#if jobStatus.status === 'running'}
							GENERATING...
						{:else if jobStatus.status === 'finished'}
							COMPLETE
						{:else if jobStatus.status === 'error'}
							ERROR
						{:else}
							PREPARING...
						{/if}
					</span>
					<span class="text-slate-400">{jobStatus.percent}%</span>
				</div>

				<div class="h-2 w-full overflow-hidden rounded-full bg-slate-800">
					<div
						class="h-full bg-sky-500 transition-all duration-500"
						style:width="{jobStatus.percent}%"
						class:bg-red-500={jobStatus.status === 'error'}
						class:bg-green-500={jobStatus.status === 'finished'}
					></div>
				</div>

				<div class="space-y-2">
					<p class="truncate text-sm font-bold text-sky-300">
						{jobStatus.currentStepText || 'Starting pipeline...'}
					</p>
					<p
						class="truncate rounded-lg border border-white/5 bg-black/40 p-2 font-mono text-xs text-slate-300"
					>
						{jobStatus.lastLine}
					</p>
				</div>

				{#if jobStatus.status === 'finished'}
					<div class="flex gap-4 pt-2">
						<a
							href={resolve('/')}
							class="flex-1 rounded-lg bg-white/10 py-2 text-center text-xs font-bold hover:bg-white/20"
							>View on Map</a
						>
						{#if mode === 'animation'}
							<a
								href={resolve('/animations')}
								class="flex-1 rounded-lg bg-sky-500/20 py-2 text-center text-xs font-bold text-sky-400 hover:bg-sky-500/30"
								>Go to Videos</a
							>
						{/if}
					</div>
				{/if}
			</div>
		{/if}
	</div>

	<!-- Right: Map -->
	<div id="map-picker" class="flex-1 bg-slate-900"></div>
</div>

<style>
	:global(.mapboxgl-ctrl-attrib) {
		display: none;
	}
</style>
