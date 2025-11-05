import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';

const INACTIVITY_THRESHOLD_MINUTES = 15;

export const GET: RequestHandler = async ({ platform }) => {
	const db = platform?.env?.DB;

	if (!db) {
		return json({ error: 'Database not available' }, { status: 500 });
	}

	try {
		// Query 1: Count pending submissions
		const pendingResult = await db
			.prepare('SELECT COUNT(*) as count FROM submissions WHERE status = ?')
			.bind('pending')
			.first<{ count: number }>();
		const pendingCount = pendingResult?.count || 0;

		// Query 2: Count processing submissions
		const processingResult = await db
			.prepare('SELECT COUNT(*) as count FROM submissions WHERE status = ?')
			.bind('processing')
			.first<{ count: number }>();
		const processingCount = processingResult?.count || 0;

		// Query 3: Get last completed timestamp
		const lastCompletedResult = await db
			.prepare('SELECT MAX(completed_at) as last_completed FROM submissions WHERE status = ?')
			.bind('completed')
			.first<{ last_completed: string | null }>();
		const lastCompleted = lastCompletedResult?.last_completed || null;

		// Calculate minutes since last completion
		let minutesSinceLastCompleted: number | null = null;
		if (lastCompleted) {
			const lastCompletedDate = new Date(lastCompleted);
			const now = new Date();
			const diffMs = now.getTime() - lastCompletedDate.getTime();
			minutesSinceLastCompleted = Math.floor(diffMs / 60000); // Convert ms to minutes
		}

		// Determine wake/sleep status
		const shouldWake = pendingCount > 0;
		const shouldSleep =
			processingCount === 0 &&
			minutesSinceLastCompleted !== null &&
			minutesSinceLastCompleted > INACTIVITY_THRESHOLD_MINUTES;

		return json({
			shouldWake,
			shouldSleep,
			pendingCount,
			processingCount,
			lastCompleted,
			minutesSinceLastCompleted
		});
	} catch (error) {
		console.error('Error fetching system status:', error);
		return json(
			{
				error: 'Failed to fetch system status',
				details: error instanceof Error ? error.message : 'Unknown error'
			},
			{ status: 500 }
		);
	}
};
