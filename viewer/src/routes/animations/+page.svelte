<script lang="ts">
	import { onMount } from 'svelte';
	import { resolve } from '$app/paths';

	let animations = $state<{ filename: string; size: string; date: string }[]>([]);
	let loading = $state(true);
	let selectedVideo = $state<string | null>(null);

	onMount(async () => {
		try {
			const response = await fetch('/api/animations');
			if (response.ok) {
				animations = await response.json();
			}
		} catch {
			console.error('Failed to fetch animations');
		} finally {
			loading = false;
		}
	});
</script>

<div class="min-h-[calc(100vh-3.5rem)] bg-slate-950 p-8 text-white">
	<div class="mx-auto max-w-6xl">
		<h2 class="mb-8 text-3xl font-bold text-sky-400">Generated Animations</h2>

		{#if loading}
			<div class="flex h-64 items-center justify-center">
				<div
					class="h-12 w-12 animate-spin rounded-full border-4 border-sky-500 border-t-transparent"
				></div>
			</div>
		{:else if animations.length === 0}
			<div class="rounded-2xl border border-white/5 bg-slate-900/50 p-12 text-center">
				<p class="text-xl text-slate-400">No animations found yet.</p>
				<a href={resolve('/create')} class="mt-4 inline-block text-sky-400 hover:underline"
					>Go create one!</a
				>
			</div>
		{:else}
			<div class="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3">
				{#each animations as anim (anim)}
					<div
						class="group relative cursor-pointer overflow-hidden rounded-2xl border border-white/10 bg-slate-900 transition-all hover:border-sky-500/50 hover:shadow-2xl hover:shadow-sky-500/10"
					>
						<div
							class="aspect-video w-full bg-slate-800"
							onclick={() => (selectedVideo = anim.filename)}
							onkeydown={(e) => e.key === 'Enter' && (selectedVideo = anim.filename)}
							role="button"
							tabindex="0"
						>
							<img
								src="/thumb/{anim.filename}.jpg"
								alt={anim.filename}
								class="h-full w-full object-cover transition-transform duration-500 group-hover:scale-105"
								loading="lazy"
							/>
							<div
								class="absolute inset-0 flex items-center justify-center bg-black/20 opacity-0 transition-opacity group-hover:opacity-100"
							>
								<svg class="h-12 w-12 text-white" viewBox="0 0 24 24" fill="currentColor"
									><path d="M8 5v14l11-7z" /></svg
								>
							</div>
						</div>
						<div class="p-4 text-left">
							<h3 class="truncate font-semibold text-white">
								<button
									type="button"
									class="w-full truncate text-left hover:text-sky-400 focus:outline-none"
									onclick={() => (selectedVideo = anim.filename)}
								>
									{anim.filename}
								</button>
							</h3>
							<div class="mt-2 flex items-center justify-between text-xs text-slate-500">
								<span>{anim.date} • {anim.size}</span>
								<a
									href={resolve(
										`/scrub/${anim.filename.replace('timelapse_', '').replace('.mp4', '')}`
									)}
									class="relative z-10 rounded-md bg-sky-500/10 px-2 py-1 font-bold text-sky-400 hover:bg-sky-500/20"
								>
									Scrub Frames
								</a>
							</div>
						</div>
					</div>
				{/each}
			</div>
		{/if}
	</div>
</div>

{#if selectedVideo}
	<div class="fixed inset-0 z-[3000] flex items-center justify-center bg-black/90 p-8">
		<button
			class="absolute top-8 right-8 text-white hover:text-sky-400"
			onclick={() => (selectedVideo = null)}
			aria-label="Close"
		>
			<svg class="h-8 w-8" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
				><path d="M18 6L6 18M6 6l12 12" /></svg
			>
		</button>
		<div class="w-full max-w-5xl">
			<video controls autoplay class="w-full rounded-2xl border border-white/10 shadow-2xl">
				<source src={resolve(`/video/${selectedVideo}`)} type="video/mp4" />
				Your browser does not support the video tag.
			</video>
			<div class="mt-4 flex justify-between">
				<h3 class="text-xl font-bold text-white">{selectedVideo}</h3>
				<a href={resolve(`/video/${selectedVideo}`)} download class="text-sky-400 hover:underline"
					>Download MP4</a
				>
			</div>
		</div>
	</div>
{/if}
