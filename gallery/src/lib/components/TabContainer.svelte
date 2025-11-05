<script lang="ts">
	import type { Snippet } from 'svelte';

	let {
		hasVideo = false,
		children,
		videoContent
	}: {
		hasVideo?: boolean;
		children?: Snippet;
		videoContent?: Snippet;
	} = $props();

	let activeTab = $state<'artwork' | 'video'>('artwork');

	function switchTab(tab: 'artwork' | 'video') {
		activeTab = tab;
	}
</script>

<div class="tab-container">
	<!-- Tab Buttons -->
	{#if hasVideo}
		<div class="flex gap-2 mb-4">
			<button
				class="flex-1 font-black text-base px-4 py-3 border-4 border-black uppercase transition-all {activeTab ===
				'artwork'
					? 'bg-kidpix-yellow text-black shadow-chunky'
					: 'bg-gray-300 text-gray-600 shadow-none hover:bg-gray-400'}"
				onclick={() => switchTab('artwork')}
			>
				🎨 Finished Artwork
			</button>
			<button
				class="flex-1 font-black text-base px-4 py-3 border-4 border-black uppercase transition-all {activeTab ===
				'video'
					? 'bg-kidpix-cyan text-black shadow-chunky'
					: 'bg-gray-300 text-gray-600 shadow-none hover:bg-gray-400'}"
				onclick={() => switchTab('video')}
			>
				🎬 Creation Process
			</button>
		</div>
	{/if}

	<!-- Tab Content -->
	<div class="tab-content">
		{#if activeTab === 'artwork'}
			<div class="artwork-tab">
				{@render children?.()}
			</div>
		{:else}
			<div class="video-tab">
				{@render videoContent?.()}
			</div>
		{/if}
	</div>
</div>
