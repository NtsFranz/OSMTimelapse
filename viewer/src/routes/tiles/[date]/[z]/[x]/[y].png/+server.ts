import { error } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import { readFileSync, existsSync } from 'fs';
import { join, resolve } from 'path';

export const GET: RequestHandler = async ({ params }) => {
	const { date, z, x, y } = params;

	// Path to tiles relative to project root
	const tilesDir = resolve('..', 'output', 'tiles');
	// y should not include .png if we use the [y].png filename
	const cleanY = (y || '').replace('.png', '');
	const tilePath = join(tilesDir, date || '', z || '', x || '', cleanY + '.png');

	if (!existsSync(tilePath)) {
		throw error(404, 'Tile not found');
	}

	try {
		const image = readFileSync(tilePath);
		return new Response(image, {
			headers: {
				'Content-Type': 'image/png',
				'Cache-Control': 'public, max-age=31536000'
			}
		});
	} catch {
		throw error(500, 'Internal server error');
	}
};
