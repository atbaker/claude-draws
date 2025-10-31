import { error } from '@sveltejs/kit';
import type { PageLoad } from './$types';

// Disable prerendering to allow runtime data fetching
export const prerender = false;

export const load: PageLoad = async ({ params, fetch }) => {
	try {
		const response = await fetch(`/api/artworks/${params.id}`);

		if (!response.ok) {
			if (response.status === 404) {
				error(404, 'Artwork not found');
			}
			error(500, 'Failed to load artwork');
		}

		const data = await response.json();

		if (!data.artwork) {
			error(404, 'Artwork not found');
		}

		return {
			artwork: data.artwork
		};
	} catch (err) {
		console.error('Error loading artwork:', err);
		error(500, 'Failed to load artwork');
	}
};
