<script lang="ts">
	import { onMount } from 'svelte';

	interface Submission {
		id: string;
		prompt: string;
		status: 'pending' | 'processing';
		created_at: string;
	}

	let submissions: Submission[] = [];
	let isLoading = true;
	let error = '';

	function truncatePrompt(prompt: string, maxLength: number = 60): string {
		if (prompt.length <= maxLength) return prompt;
		return prompt.substring(0, maxLength).trim() + '...';
	}

	onMount(async () => {
		try {
			const response = await fetch('/api/queue');
			const result = await response.json();

			if (!response.ok) {
				throw new Error(result.error || 'Failed to fetch queue');
			}

			// Get top 3 submissions
			submissions = (result.submissions || []).slice(0, 3);
		} catch (err) {
			error = err instanceof Error ? err.message : 'An error occurred';
		} finally {
			isLoading = false;
		}
	});
</script>

<div class="bg-kidpix-cyan border-4 border-black p-6 shadow-chunky-lg">
	<h2 class="text-2xl font-black uppercase mb-4 pb-4 border-b-4 border-black">
		Current Queue
	</h2>

	{#if isLoading}
		<p class="text-center font-bold text-lg">Loading queue...</p>
	{:else if error}
		<p class="text-center font-bold text-lg text-red-700">Failed to load queue</p>
	{:else if submissions.length === 0}
		<div class="text-center py-4">
			<p class="text-lg font-bold mb-4">The queue is empty!</p>
			<p class="font-bold"><a href="/submit" class="underline hover:text-kidpix-purple">Submit your request</a> and Claude Draws will get started right away.</p>
		</div>
	{:else}
		<div class="space-y-3">
			{#each submissions as submission, index}
				<div class="bg-white border-2 border-black p-4 flex items-center gap-3">
					<!-- Position Badge -->
					<div
						class="bg-kidpix-purple text-white font-black text-lg px-3 py-1 border-2 border-black min-w-[3rem] text-center flex-shrink-0"
					>
						#{index + 1}
					</div>

					<!-- Status & Prompt -->
					<div class="flex-1 min-w-0">
						{#if submission.status === 'processing'}
							<div class="mb-1">
								<span
									class="inline-block bg-kidpix-green text-black font-black text-xs px-2 py-1 border border-black uppercase"
								>
									Processing
								</span>
							</div>
						{/if}
						<p class="text-sm font-bold text-gray-800 truncate">
							{truncatePrompt(submission.prompt)}
						</p>
					</div>
				</div>
			{/each}
		</div>

		<!-- See all requests button -->
		<div class="mt-6 text-center">
			<a
				href="/queue"
				class="inline-block bg-kidpix-purple text-white font-bold text-lg px-6 py-3 border-4 border-black shadow-chunky hover:shadow-chunky-hover hover:translate-x-1 hover:translate-y-1 active:translate-x-2 active:translate-y-2 active:shadow-none uppercase transition-all"
			>
				See all requests
			</a>
		</div>
	{/if}
</div>
