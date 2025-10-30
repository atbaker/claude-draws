import galleryMetadata from '$lib/gallery-metadata.json';
import type { PageLoad } from './$types';

// Disable prerendering to allow runtime queue fetching
export const prerender = false;

export const load: PageLoad = () => {
	return {
		artworks: galleryMetadata.artworks
	};
};
