import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';

export const POST: RequestHandler = async ({ request, platform }) => {
	try {
		// Get request data
		const { submissionId, increment } = await request.json();

		// Validate submission ID
		if (!submissionId || typeof submissionId !== 'string') {
			return json({ error: 'Submission ID is required' }, { status: 400 });
		}

		// Validate increment value (should be 1 for upvote, -1 for un-upvote)
		if (typeof increment !== 'number' || (increment !== 1 && increment !== -1)) {
			return json({ error: 'Invalid increment value' }, { status: 400 });
		}

		// Get platform bindings
		if (!platform?.env?.DB) {
			return json({ error: 'Database not available' }, { status: 500 });
		}

		const db = platform.env.DB;

		// Update upvote count
		try {
			const result = await db
				.prepare(
					`UPDATE submissions
					SET upvote_count = upvote_count + ?
					WHERE id = ? AND status IN ('pending', 'processing')
					RETURNING upvote_count`
				)
				.bind(increment, submissionId)
				.first();

			if (!result) {
				return json({ error: 'Submission not found or not in pending/processing status' }, { status: 404 });
			}

			return json({
				success: true,
				upvoteCount: result.upvote_count
			});
		} catch (error) {
			console.error('Failed to update upvote count:', error);
			return json({ error: 'Failed to update upvote' }, { status: 500 });
		}
	} catch (error) {
		console.error('Unexpected error in upvote API:', error);
		return json({ error: 'An unexpected error occurred' }, { status: 500 });
	}
};
