import { error } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import { existsSync, readdirSync, readFileSync } from 'fs';
import { resolve, join } from 'path';
import { execSync } from 'child_process';

export const GET: RequestHandler = async ({ params }) => {
	const { filename } = params;
	if (!filename) throw error(400, 'Filename required');

	const videoName = filename.replace('.jpg', '');
	const projectRoot = resolve('..');
	const videoPath = join(projectRoot, 'output', videoName);
	const thumbDir = join(projectRoot, 'output', 'thumbnails');
	const thumbPath = join(thumbDir, `${videoName}.jpg`);

	if (!existsSync(videoPath)) {
		throw error(404, 'Video not found');
	}

	// Strategy 1: Use the first rendered frame (fastest, no FFmpeg needed)
	const cacheKey = videoName.replace('timelapse_', '').replace('.mp4', '');
	const framesDir = join(projectRoot, 'output', 'frames', cacheKey);

	if (existsSync(framesDir)) {
		const firstFrame = readdirSync(framesDir).find((f) => f.endsWith('.png'));
		if (firstFrame) {
			try {
				// Just copy the frame or serve it directly as JPEG (most browsers handle PNG in .jpg ext if header is correct)
				const framePath = join(framesDir, firstFrame);
				const image = readFileSync(framePath);
				return new Response(image, {
					headers: {
						'Content-Type': 'image/png', // Actually PNG but served at .jpg route
						'Cache-Control': 'public, max-age=31536000'
					}
				});
			} catch (e) {
				console.warn('Failed to read frame for thumbnail:', e);
			}
		}
	}

	// Strategy 2: Fallback to FFmpeg (only if frames dir is missing/empty)
	if (!existsSync(thumbPath)) {
		try {
			const cmd = `ffmpeg -ss 00:00:01 -i "${videoPath}" -vframes 1 -q:v 2 "${thumbPath}" -y`;
			execSync(cmd, { stdio: 'ignore' });
		} catch (e) {
			console.error('FFmpeg thumbnail failed:', e);
			// If all fails, return a 404 or a placeholder
			throw error(500, 'Thumbnail generation failed');
		}
	}

	try {
		const image = readFileSync(thumbPath);
		return new Response(image, {
			headers: {
				'Content-Type': 'image/jpeg',
				'Cache-Control': 'public, max-age=31536000'
			}
		});
	} catch {
		throw error(500, 'Failed to read thumbnail');
	}
};
