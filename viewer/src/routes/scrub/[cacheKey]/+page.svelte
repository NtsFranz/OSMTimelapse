<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/state';

	const cacheKey = page.params.cacheKey;
	let frames = $state<{ filename: string; date: string }[]>([]);
	let currentIndex = $state(0);
	let loading = $state(true);

	onMount(async () => {
		try {
			const res = await fetch(`/api/frames/${cacheKey}`);
			if (res.ok) {
				const data = await res.json();
				frames = data.frames;
			}
		} catch (e) {
			console.error('Failed to load frames');
		} finally {
			loading = false;
		}
	});

	let currentFrame = $derived(frames[currentIndex]);
</script>

<div class="min-h-[calc(100vh-3.5rem)] bg-slate-950 p-8 text-white">
	<div class="mx-auto max-w-6xl">
		<div class="mb-8 flex items-center justify-between">
			<div>
				<h2 class="text-3xl font-bold text-sky-400">Frame Explorer</h2>
				<p class="font-mono text-sm text-slate-500">{cacheKey}</p>
			</div>
			<a
				href="/animations"
				class="rounded-lg bg-white/5 px-4 py-2 text-sm font-bold hover:bg-white/10"
				>Back to Gallery</a
			>
		</div>

		{#if loading}
			<div class="flex h-[60vh] items-center justify-center">
				<div
					class="h-12 w-12 animate-spin rounded-full border-4 border-sky-500 border-t-transparent"
				></div>
			</div>
		{:else if frames.length === 0}
			<div class="rounded-2xl border border-white/5 bg-slate-900/50 p-12 text-center">
				<p class="text-xl text-slate-400">No frames found for this job.</p>
			</div>
		{:else}
			<div class="space-y-8">
				<div
					class="group relative overflow-hidden rounded-3xl border border-white/10 bg-black shadow-2xl"
				>
					<img
						src="/frame/{cacheKey}/{currentFrame.filename}"
						alt="Frame {currentFrame.date}"
						class="max-h-[70vh] w-full object-contain"
					/>

					<div
						class="absolute bottom-6 left-1/2 -translate-x-1/2 rounded-full border border-white/10 bg-black/60 px-6 py-2 backdrop-blur-md"
					>
						<span class="text-lg font-bold text-sky-400">{currentFrame.date}</span>
						<span class="ml-2 text-xs text-slate-400">({currentIndex + 1} / {frames.length})</span>
					</div>
				</div>

				<div class="rounded-2xl border border-white/10 bg-slate-900/50 p-6 backdrop-blur-md">
					<div class="mb-4 flex items-center justify-between">
						<span class="text-sm font-medium text-slate-400">Scrub Timeline</span>
						<div class="flex gap-2">
							<button
								class="rounded-lg bg-white/5 p-2 hover:bg-white/10 disabled:opacity-20"
								onclick={() => currentIndex--}
								disabled={currentIndex === 0}
							>
								<svg
									class="h-5 w-5"
									viewBox="0 0 24 24"
									fill="none"
									stroke="currentColor"
									stroke-width="2"><path d="M15 18l-6-6 6-6" /></svg
								>
							</button>
							<button
								class="rounded-lg bg-white/5 p-2 hover:bg-white/10 disabled:opacity-20"
								onclick={() => currentIndex++}
								disabled={currentIndex === frames.length - 1}
							>
								<svg
									class="h-5 w-5"
									viewBox="0 0 24 24"
									fill="none"
									stroke="currentColor"
									stroke-width="2"><path d="M9 5l6 6-6 6" /></svg
								>
							</button>
						</div>
					</div>

					<input
						type="range"
						min="0"
						max={frames.length - 1}
						bind:value={currentIndex}
						class="w-full cursor-pointer accent-sky-500"
					/>
				</div>
			</div>
		{/if}
	</div>
</div>

<style>
	input[type='range'] {
		-webkit-appearance: none;
		appearance: none;
		height: 8px;
		background: rgba(255, 255, 255, 0.1);
		border-radius: 4px;
	}

	input[type='range']::-webkit-slider-thumb {
		-webkit-appearance: none;
		height: 24px;
		width: 24px;
		background: #38bdf8;
		border-radius: 50%;
		box-shadow: 0 0 20px rgba(56, 189, 248, 0.4);
	}
</style>
