import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import { readdirSync, statSync, existsSync } from 'fs';
import { resolve } from 'path';

export const GET: RequestHandler = async () => {
	const outputDir = resolve('..', 'output');

	if (!existsSync(outputDir)) {
		return json([]);
	}

	try {
		const files = readdirSync(outputDir);
		const animations = files
			.filter((f) => f.endsWith('.mp4'))
			.map((f) => {
				const stats = statSync(resolve(outputDir, f));
				return {
					filename: f,
					size: `${(stats.size / (1024 * 1024)).toFixed(1)} MB`,
					date: stats.mtime.toISOString().split('T')[0],
					mtime: stats.mtimeMs
				};
			})
			.sort((a, b) => b.mtime - a.mtime);

		return json(animations);
	} catch (e) {
		console.error('Error listing animations:', e);
		return json([]);
	}
};
