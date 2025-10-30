import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';

export const GET: RequestHandler = async ({ platform }) => {
	const db = platform?.env?.DB;

	if (!db) {
		return json({ error: 'Database not available' }, { status: 500 });
	}

	try {
		const result = await db
			.prepare(
				`SELECT id, prompt, status, created_at
				FROM submissions
				WHERE status IN ('pending', 'processing')
				ORDER BY created_at ASC`
			)
			.all();

		return json({
			success: true,
			submissions: result.results || []
		});
	} catch (error) {
		console.error('Error fetching queue:', error);
		return json(
			{
				error: 'Failed to fetch queue',
				details: error instanceof Error ? error.message : 'Unknown error'
			},
			{ status: 500 }
		);
	}
};
