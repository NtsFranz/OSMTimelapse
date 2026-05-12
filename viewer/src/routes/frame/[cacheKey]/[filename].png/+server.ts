import { error } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import { readFileSync, existsSync } from 'fs';
import { resolve, join } from 'path';

export const GET: RequestHandler = async ({ params }) => {
	const { cacheKey, filename } = params;
	if (!cacheKey || !filename) throw error(400, 'Missing parameters');

	const projectRoot = resolve('..');
	const framePath = join(projectRoot, 'output', 'frames', cacheKey, `${filename}.png`);
	console.log(framePath);

	if (!existsSync(framePath)) {
		throw error(404, 'Frame not found');
	}

	try {
		const image = readFileSync(framePath);
		return new Response(image, {
			headers: {
				'Content-Type': 'image/png',
				'Cache-Control': 'public, max-age=31536000'
			}
		});
	} catch {
		throw error(500, 'Failed to read frame');
	}
};
