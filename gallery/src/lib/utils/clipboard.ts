/**
 * Copy text to clipboard and return success status
 */
export async function copyToClipboard(text: string): Promise<boolean> {
	try {
		await navigator.clipboard.writeText(text);
		return true;
	} catch (err) {
		console.error('Failed to copy to clipboard:', err);
		return false;
	}
}

/**
 * Get the canonical URL for the current page (without query params or hash)
 */
export function getCanonicalUrl(): string {
	if (typeof window === 'undefined') return '';
	return window.location.origin + window.location.pathname;
}
