import galleryMetadata from '$lib/gallery-metadata.json';
import { error } from '@sveltejs/kit';
import type { PageLoad } from './$types';

// Prerender all artwork pages at build time
export const prerender = true;

// Tell SvelteKit which artwork IDs to prerender
export function entries() {
	return galleryMetadata.artworks.map((artwork) => ({
		id: artwork.id
	}));
}

export const load: PageLoad = ({ params }) => {
	const artwork = galleryMetadata.artworks.find((a) => a.id === params.id);

	if (!artwork) {
		error(404, 'Artwork not found');
	}

	return {
		artwork
	};
};
