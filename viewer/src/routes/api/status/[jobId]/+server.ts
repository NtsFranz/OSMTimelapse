import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import { readFileSync, existsSync } from 'fs';
import { resolve } from 'path';

export const GET: RequestHandler = async ({ params }) => {
	const { jobId } = params;
	const logPath = resolve('..', 'output', `${jobId}.log`);

	if (!existsSync(logPath)) {
		return json({ status: 'waiting' });
	}

	try {
		const content = readFileSync(logPath, 'utf-8');
		const lines = content.split('\n');

		let progress = 0;
		let totalSteps = 0;
		let currentStepText = '';
		let status = 'running';

		// Check for success or error (case-insensitive)
		const lowerContent = content.toLowerCase();
		if (
			lowerContent.includes('pipeline complete') ||
			lowerContent.includes('video:') ||
			lowerContent.includes('tiles generated in:')
		) {
			status = 'finished';
		} else if (
			lowerContent.includes('traceback') ||
			lowerContent.includes('error:') ||
			lowerContent.includes('[error]')
		) {
			status = 'error';
		}

		// Pattern: [1/7] Processing 2020-01-01 ...
		const progressRegex = /\[(\d+)\/(\d+)\] Processing/;

		for (let i = lines.length - 1; i >= 0; i--) {
			const line = lines[i];
			const match = line.match(progressRegex);
			if (match) {
				progress = parseInt(match[1]);
				totalSteps = parseInt(match[2]);
				// Extract everything after the progress indicator
				currentStepText = line.substring(line.indexOf('] ') + 2).replace(/^\[\d+\/\d+\]\s*/, '');
				break;
			}
		}

		// If finished, force progress to 100%
		if (status === 'finished' && totalSteps > 0) {
			progress = totalSteps;
		}

		return json({
			status,
			progress,
			totalSteps,
			currentStepText:
				currentStepText ||
				(status === 'finished' ? 'Generation complete!' : 'Starting pipeline...'),
			percent:
				totalSteps > 0
					? Math.round((progress / totalSteps) * 100)
					: status === 'finished'
						? 100
						: 0,
			lastLine: lines.filter((l) => l.trim()).pop() || ''
		});
	} catch (e) {
		console.error('Status API Error:', e);
		return json({ status: 'error', error: 'Failed to read log' });
	}
};
