<script lang="ts">
	import type { PageData } from './$types';

	let { data }: { data: PageData } = $props();
	const { artwork } = data;
</script>

<svelte:head>
	<title>{artwork.title} - Claude Draws</title>
	<meta name="description" content={`${artwork.title} - AI-generated Kid Pix art`} />
	<meta property="og:title" content={artwork.title} />
	<meta property="og:description" content="AI-generated Kid Pix art" />
	<meta property="og:image" content={artwork.imageUrl} />
	<meta property="og:type" content="website" />
</svelte:head>

<div class="container mx-auto px-4 py-8">
	<div class="mb-6">
		<a href="/" class="text-blue-600 hover:text-blue-800 transition-colors">
			← Back to Gallery
		</a>
	</div>

	<div class="max-w-4xl mx-auto bg-white rounded-lg shadow-lg overflow-hidden">
		<div class="bg-gray-100 p-8">
			<img
				src={artwork.imageUrl}
				alt={artwork.title}
				class="w-full h-auto pixelated mx-auto"
			/>
		</div>

		<div class="p-8">
			<h1 class="text-3xl font-bold mb-4">{artwork.title}</h1>

			<div class="space-y-4 text-gray-700">
				<div>
					<h2 class="text-sm font-semibold text-gray-500 uppercase mb-1">Created</h2>
					<time class="text-lg">
						{new Date(artwork.createdAt).toLocaleString('en-US', {
							dateStyle: 'full',
							timeStyle: 'short'
						})}
					</time>
				</div>

				{#if artwork.redditPostUrl}
					<div>
						<h2 class="text-sm font-semibold text-gray-500 uppercase mb-1">Inspired By</h2>
						<a
							href={artwork.redditPostUrl}
							target="_blank"
							rel="noopener noreferrer"
							class="text-lg text-blue-600 hover:text-blue-800 transition-colors"
						>
							View Reddit Post →
						</a>
					</div>
				{/if}

				{#if artwork.videoUrl}
					<div>
						<h2 class="text-sm font-semibold text-gray-500 uppercase mb-1">
							Creation Process
						</h2>
						<a
							href={artwork.videoUrl}
							target="_blank"
							rel="noopener noreferrer"
							class="text-lg text-blue-600 hover:text-blue-800 transition-colors"
						>
							Watch Video →
						</a>
					</div>
				{/if}
			</div>

			<div class="mt-8 pt-8 border-t border-gray-200">
				<p class="text-sm text-gray-600">
					This artwork was created by Claude for Chrome using Kid Pix.
				</p>
			</div>
		</div>
	</div>
</div>
