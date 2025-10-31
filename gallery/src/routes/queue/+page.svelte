<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import Header from '$lib/components/Header.svelte';
	import Footer from '$lib/components/Footer.svelte';

	interface Submission {
		id: string;
		prompt: string;
		status: 'pending' | 'processing';
		created_at: string;
		upvote_count: number;
	}

	let submissions: Submission[] = [];
	let isLoading = true;
	let error = '';
	let highlightId: string | null = null;
	let expandedSubmissionId: string | null = null;
	let upvotedSubmissions: string[] = [];
	let mySubmissions: string[] = [];

	function getRelativeTime(timestamp: string): string {
		const now = new Date();
		const created = new Date(timestamp);
		const diffMs = now.getTime() - created.getTime();
		const diffMins = Math.floor(diffMs / 60000);
		const diffHours = Math.floor(diffMins / 60);
		const diffDays = Math.floor(diffHours / 24);

		if (diffMins < 1) return 'Just now';
		if (diffMins < 60) return `${diffMins} minute${diffMins === 1 ? '' : 's'} ago`;
		if (diffHours < 24) return `${diffHours} hour${diffHours === 1 ? '' : 's'} ago`;
		return `${diffDays} day${diffDays === 1 ? '' : 's'} ago`;
	}

	function truncatePrompt(prompt: string, maxLength: number = 200): string {
		if (prompt.length <= maxLength) return prompt;
		return prompt.substring(0, maxLength).trim() + '...';
	}

	function toggleExpand(submissionId: string) {
		// If clicking the already-expanded one, collapse it
		// Otherwise, expand this one (automatically collapsing any other)
		expandedSubmissionId = expandedSubmissionId === submissionId ? null : submissionId;
	}

	function hasUpvoted(submissionId: string): boolean {
		return upvotedSubmissions.includes(submissionId);
	}

	function isMySubmission(submissionId: string): boolean {
		return mySubmissions.includes(submissionId);
	}

	function canUpvote(submissionId: string): boolean {
		return !isMySubmission(submissionId);
	}

	async function handleUpvote(submission: Submission) {
		const alreadyUpvoted = hasUpvoted(submission.id);
		const increment = alreadyUpvoted ? -1 : 1;

		try {
			const response = await fetch('/api/upvote', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ submissionId: submission.id, increment })
			});

			const result = await response.json();

			if (!response.ok) {
				throw new Error(result.error || 'Failed to update upvote');
			}

			// Update local state and trigger Svelte reactivity
			submissions = submissions.map(s =>
				s.id === submission.id
					? { ...s, upvote_count: result.upvoteCount }
					: s
			);

			// Update upvoted list
			if (alreadyUpvoted) {
				upvotedSubmissions = upvotedSubmissions.filter(id => id !== submission.id);
			} else {
				upvotedSubmissions = [...upvotedSubmissions, submission.id];
			}

			// Save to localStorage
			localStorage.setItem('upvotedSubmissions', JSON.stringify(upvotedSubmissions));
		} catch (err) {
			console.error('Error updating upvote:', err);
		}
	}

	onMount(async () => {
		// Load localStorage data
		const storedUpvotes = localStorage.getItem('upvotedSubmissions');
		if (storedUpvotes) {
			try {
				upvotedSubmissions = JSON.parse(storedUpvotes);
			} catch (e) {
				console.error('Failed to parse upvoted submissions:', e);
			}
		}

		const storedMySubmissions = localStorage.getItem('mySubmissions');
		if (storedMySubmissions) {
			try {
				mySubmissions = JSON.parse(storedMySubmissions);
			} catch (e) {
				console.error('Failed to parse my submissions:', e);
			}
		}

		highlightId = $page.url.searchParams.get('highlight');

		try {
			const response = await fetch('/api/queue');
			const result = await response.json();

			if (!response.ok) {
				throw new Error(result.error || 'Failed to fetch queue');
			}

			submissions = result.submissions || [];
		} catch (err) {
			error = err instanceof Error ? err.message : 'An error occurred';
		} finally {
			isLoading = false;
		}

		// Scroll to highlighted submission after render
		if (highlightId) {
			setTimeout(() => {
				const element = document.getElementById(`submission-${highlightId}`);
				if (element) {
					element.scrollIntoView({ behavior: 'smooth', block: 'center' });
				}
			}, 100);
		}
	});
</script>

<svelte:head>
	<title>Queue - Claude Draws</title>
	<meta
		name="description"
		content="View the current queue of artwork requests for Claude Draws. See where your submission stands!"
	/>
</svelte:head>

<div class="min-h-screen">
	<Header />

	<!-- Navigation Bar -->
	<nav class="bg-kidpix-purple border-b-4 border-black p-4">
		<div class="container mx-auto flex justify-between items-center">
			<a
				href="/"
				class="bg-kidpix-yellow text-black font-bold text-lg px-4 py-2 border-4 border-black shadow-chunky hover:shadow-chunky-hover hover:translate-x-1 hover:translate-y-1 active:translate-x-2 active:translate-y-2 active:shadow-none uppercase transition-all"
			>
				← Back
			</a>
			<p class="text-white font-bold text-xl text-center uppercase hidden sm:block">
				Request Queue
			</p>
		</div>
	</nav>

	<!-- Main Content -->
	<main class="container mx-auto p-4 sm:p-8">
		<div class="max-w-4xl mx-auto">
			<!-- Introduction -->
			<div class="bg-kidpix-cyan border-4 border-black p-6 sm:p-8 shadow-chunky-lg mb-8">
				<h1 class="text-3xl font-black uppercase mb-4 pb-4 border-b-4 border-black">
					Request Queue
				</h1>
				<p class="text-lg font-bold">
					Claude Draws processes the most-upvoted requests first. When submissions have the same number of upvotes, the oldest is processed first. <a href="/submit" class="underline hover:text-kidpix-purple">Submit your request here</a>.
				</p>
			</div>

			<!-- Loading State -->
			{#if isLoading}
				<div class="bg-white border-4 border-black p-8 shadow-chunky-lg text-center">
					<p class="text-2xl font-black uppercase">Loading queue...</p>
				</div>
			{/if}

			<!-- Error State -->
			{#if error}
				<div class="bg-kidpix-red border-4 border-black p-6 shadow-chunky-lg">
					<h2 class="text-2xl font-black uppercase mb-4 text-white">Error</h2>
					<p class="text-white font-bold text-lg">{error}</p>
				</div>
			{/if}

			<!-- Empty Queue -->
			{#if !isLoading && !error && submissions.length === 0}
				<div class="bg-kidpix-green border-4 border-black p-8 shadow-chunky-lg text-center">
					<h2 class="text-2xl font-black uppercase mb-4">Queue is Empty!</h2>
					<p class="text-lg font-bold mb-6">
						There are no pending requests right now. Want to submit one?
					</p>
					<a
						href="/submit"
						class="inline-block bg-kidpix-purple text-white font-bold text-lg px-6 py-3 border-4 border-black shadow-chunky hover:shadow-chunky-hover hover:translate-x-1 hover:translate-y-1 active:translate-x-2 active:translate-y-2 active:shadow-none uppercase transition-all"
					>
						Submit a Request
					</a>
				</div>
			{/if}

			<!-- Queue List -->
			{#if !isLoading && !error && submissions.length > 0}
				<div class="space-y-4">
					{#each submissions as submission, index}
						<div
							id="submission-{submission.id}"
							class="bg-white border-4 border-black p-6 shadow-chunky transition-all {highlightId === submission.id ? 'bg-kidpix-yellow animate-stamp' : ''}"
						>
							<div class="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
								<!-- Left Side: Position, Status, Timestamp -->
								<div class="flex items-center gap-4">
									<div class="bg-kidpix-purple text-white font-black text-2xl px-4 py-2 border-4 border-black min-w-[4rem] text-center flex-shrink-0">
										#{index + 1}
									</div>
									<div>
										{#if submission.status === 'processing'}
											<span class="inline-block bg-kidpix-green text-black font-black text-sm px-3 py-1 border-2 border-black uppercase mb-2">
												Processing Now
											</span>
										{:else}
											<span class="inline-block bg-gray-300 text-black font-black text-sm px-3 py-1 border-2 border-black uppercase mb-2">
												Pending
											</span>
										{/if}
										<p class="text-sm font-bold text-gray-600 uppercase">
											{getRelativeTime(submission.created_at)}
										</p>
									</div>
								</div>

								<!-- Upvote Button -->
								<button
									on:click={() => handleUpvote(submission)}
									disabled={!canUpvote(submission.id)}
									class="flex flex-col items-center gap-1 px-4 py-3 border-4 border-black flex-shrink-0 transition-all {hasUpvoted(submission.id)
										? 'bg-kidpix-purple text-white'
										: 'bg-white hover:bg-gray-100'} {!canUpvote(submission.id) ? 'opacity-50 cursor-not-allowed' : 'hover:shadow-chunky'}"
									title={isMySubmission(submission.id) ? 'This is your submission' : hasUpvoted(submission.id) ? 'Click to remove upvote' : 'Click to upvote'}
								>
									<span class="text-2xl">▲</span>
									<span class="text-sm font-black">{submission.upvote_count}</span>
								</button>
							</div>

							<!-- Prompt -->
							<div class="mt-4 pt-4 border-t-2 border-gray-300">
								<p class="text-lg font-bold text-gray-800">
									{#if expandedSubmissionId === submission.id}
										{submission.prompt}
									{:else}
										{truncatePrompt(submission.prompt, 200)}
									{/if}
									{#if submission.prompt.length > 200}
										<button
											on:click={() => toggleExpand(submission.id)}
											class="text-kidpix-purple hover:underline ml-1"
										>
											{expandedSubmissionId === submission.id ? 'see less' : 'see more'}
										</button>
									{/if}
								</p>
							</div>

							<!-- Highlight Message -->
							{#if highlightId === submission.id}
								<div class="mt-4 pt-4 border-t-2 border-gray-300">
									<p class="text-sm font-black uppercase text-kidpix-purple">
										👆 This is your submission!
									</p>
								</div>
							{/if}
						</div>
					{/each}
				</div>
			{/if}
		</div>
	</main>

	<Footer />
</div>
