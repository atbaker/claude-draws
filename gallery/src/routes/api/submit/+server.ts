import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';

const MAX_PROMPT_LENGTH = 2000;

export const POST: RequestHandler = async ({ request, platform }) => {
	try {
		// Get form data
		const formData = await request.formData();
		const prompt = formData.get('prompt') as string;
		const email = (formData.get('email') as string) || null;

		// Validate prompt
		if (!prompt || prompt.trim().length === 0) {
			return json({ error: 'Prompt is required' }, { status: 400 });
		}

		if (prompt.length > MAX_PROMPT_LENGTH) {
			return json(
				{ error: `Prompt must be less than ${MAX_PROMPT_LENGTH} characters` },
				{ status: 400 }
			);
		}

		// Validate email (if provided)
		if (email && email.length > 0) {
			const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
			if (!emailRegex.test(email)) {
				return json({ error: 'Invalid email address' }, { status: 400 });
			}
		}

		// Get platform bindings
		if (!platform?.env?.DB) {
			console.error('Platform bindings not available:', {
				hasDB: !!platform?.env?.DB
			});
			return json({ error: 'Service temporarily unavailable' }, { status: 503 });
		}

		const db = platform.env.DB;

		// Generate submission ID
		const submissionId = `submission-${Date.now()}-${Math.random().toString(36).substring(7)}`;
		const createdAt = new Date().toISOString();

		// Insert submission into D1
		try {
			await db
				.prepare(
					`INSERT INTO submissions (id, prompt, email, status, created_at)
					VALUES (?, ?, ?, ?, ?)`
				)
				.bind(
					submissionId,
					prompt,
					email,
					'pending',
					createdAt
				)
				.run();
		} catch (error) {
			console.error('Failed to insert submission into D1:', error);
			return json({ error: 'Failed to save submission' }, { status: 500 });
		}

		// Send admin notification email (don't fail submission if this fails)
		try {
			const adminEmail = platform.env.ADMIN_NOTIFICATION_EMAIL;
			const resendApiKey = platform.env.RESEND_API_KEY;

			if (adminEmail && resendApiKey) {
				await fetch('https://api.resend.com/emails', {
					method: 'POST',
					headers: {
						'Authorization': `Bearer ${resendApiKey}`,
						'Content-Type': 'application/json'
					},
					body: JSON.stringify({
						from: 'Claude Draws <noreply@notifications.claudedraws.com>',
						to: [adminEmail],
						subject: 'New Claude Draws Submission',
						html: `
							<html>
								<body style="font-family: sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
									<h2 style="color: #882FF6;">New Submission Received</h2>
									<p><strong>Submission ID:</strong> ${submissionId}</p>
									<p><strong>Created:</strong> ${new Date(createdAt).toLocaleString()}</p>
									<p><strong>User Email:</strong> ${email || 'Not provided'}</p>
									<p><strong>Prompt:</strong></p>
									<pre style="background-color: #f5f5f5; padding: 15px; border-radius: 4px; white-space: pre-wrap; word-wrap: break-word;">${prompt}</pre>
								</body>
							</html>
						`
					})
				});
				console.log(`Admin notification sent for submission ${submissionId}`);
			}
		} catch (error) {
			console.error('Failed to send admin notification:', error);
			// Don't fail the submission if notification fails
		}

		return json({
			success: true,
			submissionId,
			message: 'Submission received successfully'
		});
	} catch (error) {
		console.error('Unexpected error in submit API:', error);
		return json({ error: 'An unexpected error occurred' }, { status: 500 });
	}
};
