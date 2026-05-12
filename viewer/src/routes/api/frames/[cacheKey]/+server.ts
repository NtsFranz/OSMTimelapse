import { json, error } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import { readdirSync, existsSync } from 'fs';
import { resolve, join } from 'path';

export const GET: RequestHandler = async ({ params }) => {
	const { cacheKey } = params;
	if (!cacheKey) throw error(400, 'Cache key required');

	const projectRoot = resolve('..');
	const framesDir = join(projectRoot, 'output', 'frames', cacheKey);

	if (!existsSync(framesDir)) {
		throw error(404, 'Frames directory not found');
	}

	try {
		const frames = readdirSync(framesDir)
			.filter((f) => f.endsWith('.png'))
			.sort() // frame_2020-01-01.png, etc.
			.map((f) => ({
				filename: f,
				date: f.replace('frame_', '').replace('.png', '')
			}));

		return json({
			cacheKey,
			frames
		});
	} catch {
		throw error(500, 'Failed to list frames');
	}
};
