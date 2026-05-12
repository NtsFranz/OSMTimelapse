<script lang="ts">
	import './layout.css';
	import favicon from '$lib/assets/favicon.svg';
	import { resolve } from '$app/paths';

	let { children } = $props();
</script>

<svelte:head>
	<link rel="icon" href={favicon} />
	<title>OSM Timelapse Viewer</title>
</svelte:head>

<nav
	class="fixed top-0 right-0 left-0 z-[2000] flex h-14 items-center justify-between border-b border-white/10 bg-slate-900/80 px-6 backdrop-blur-md"
>
	<div class="flex items-center gap-2">
		<div
			class="flex h-8 w-8 items-center justify-center rounded-lg bg-sky-500 font-bold text-slate-900"
		>
			OSM
		</div>
		<span class="text-sm font-bold tracking-tight text-white">TIMELAPSE</span>
	</div>
	<div class="flex gap-6 text-sm font-medium">
		<a href={resolve('/')} class="text-slate-400 transition-colors hover:text-sky-400"
			>Timeline Viewer</a
		>
		<a href={resolve('/create')} class="text-slate-400 transition-colors hover:text-sky-400"
			>Generate New</a
		>
		<a href={resolve('/animations')} class="text-slate-400 transition-colors hover:text-sky-400"
			>Animations</a
		>
	</div>
	<div class="w-24"></div>
	<!-- Spacer -->
</nav>

<div class="pt-14">
	{@render children()}
</div>
