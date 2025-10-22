import galleryMetadata from '$lib/gallery-metadata.json';
import type { PageLoad } from './$types';

// Prerender this page at build time
export const prerender = true;

export const load: PageLoad = () => {
	return {
		artworks: galleryMetadata.artworks
	};
};
