import { error } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import { createReadStream, existsSync, statSync } from 'fs';
import { resolve } from 'path';

export const GET: RequestHandler = async ({ params, request }) => {
	const { filename } = params;
	const filePath = resolve('..', 'output', filename || '');

	if (!existsSync(filePath)) {
		throw error(404, 'Video not found');
	}

	const stats = statSync(filePath);
	const range = request.headers.get('range');

	if (range) {
		const parts = range.replace(/bytes=/, '').split('-');
		const start = parseInt(parts[0], 10);
		const end = parts[1] ? parseInt(parts[1], 10) : stats.size - 1;
		const chunksize = end - start + 1;
		const file = createReadStream(filePath, { start, end });

		return new Response(file as any, {
			status: 206,
			headers: {
				'Content-Range': `bytes ${start}-${end}/${stats.size}`,
				'Accept-Ranges': 'bytes',
				'Content-Length': chunksize.toString(),
				'Content-Type': 'video/mp4'
			}
		});
	} else {
		const file = createReadStream(filePath);
		return new Response(file as any, {
			headers: {
				'Content-Length': stats.size.toString(),
				'Content-Type': 'video/mp4'
			}
		});
	}
};
