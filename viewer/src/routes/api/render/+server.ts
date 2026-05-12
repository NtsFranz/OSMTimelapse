import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import { spawn } from 'child_process';
import { resolve } from 'path';
import { createWriteStream } from 'fs';

export const POST: RequestHandler = async ({ request }) => {
	const { lat, lon, radius, interval, startDate, endDate, mode, tileZooms } = await request.json();

	if (!lat || !lon) {
		return json({ error: 'Latitude and Longitude are required' }, { status: 400 });
	}

	// Build the command
	// If running on host, we use 'docker compose run renderer'
	// If running inside container, we use 'uv run'
	const isInsideContainer = process.env.IS_DOCKER_CONTAINER === 'true';

	let cmd = 'uv';
	let args = [
		'run',
		'osm-timelapse',
		'render',
		'--center',
		`${lat},${lon}`,
		'--radius',
		radius.toString(),
		'--interval',
		interval,
		'--start-date',
		startDate,
		'--end-date',
		endDate
	];

	if (!isInsideContainer) {
		cmd = 'docker';
		args = [
			'compose',
			'run',
			'renderer',
			'render',
			'--center',
			`${lat},${lon}`,
			'--radius',
			radius.toString(),
			'--interval',
			interval,
			'--start-date',
			startDate,
			'--end-date',
			endDate
		];
	}

	if (mode === 'tiles') {
		args.push('--tiles');
		if (tileZooms && tileZooms.length > 0) {
			args.push('--tile-zooms', tileZooms.join(','));
		}
	}

	// Create a unique job ID based on timestamp and coordinates
	const jobId = `job_${Date.now()}`;
	const projectRoot = resolve('..');
	const logFile = resolve(projectRoot, 'output', `${jobId}.log`);
	const logStream = createWriteStream(logFile);

	console.log(`Running command: ${cmd} ${args.join(' ')} in ${projectRoot}`);
	console.log(`Logging to: ${logFile}`);

	// Spawn the process in the background
	const child = spawn(cmd, args, {
		cwd: projectRoot,
		detached: true,
		stdio: ['ignore', 'pipe', 'pipe'],
		env: process.env
	});

	child.stdout.pipe(logStream);
	child.stderr.pipe(logStream);

	child.unref();

	// We don't wait for it to finish, just confirm it started
	return json({
		message: 'Job started successfully',
		jobId,
		logFile: `${jobId}.log`
	});
};
