<script lang="ts">
	import { goto } from '$app/navigation';
	import Header from '$lib/components/Header.svelte';
	import Footer from '$lib/components/Footer.svelte';

	let prompt = '';
	let email = '';
	let isSubmitting = false;
	let submitSuccess = false;
	let submitError = '';

	async function handleSubmit(event: Event) {
		event.preventDefault();
		isSubmitting = true;
		submitError = '';

		try {
			const formData = new FormData();
			formData.append('prompt', prompt);
			if (email) {
				formData.append('email', email);
			}

			const response = await fetch('/api/submit', {
				method: 'POST',
				body: formData
			});

			const result = await response.json();

			if (!response.ok) {
				throw new Error(result.error || 'Failed to submit request');
			}

			// Store submission ID in localStorage
			if (result.submissionId) {
				const storedSubmissions = localStorage.getItem('mySubmissions');
				let mySubmissions: string[] = [];

				if (storedSubmissions) {
					try {
						mySubmissions = JSON.parse(storedSubmissions);
					} catch (e) {
						console.error('Failed to parse my submissions:', e);
					}
				}

				// Add new submission ID if not already present
				if (!mySubmissions.includes(result.submissionId)) {
					mySubmissions.push(result.submissionId);
					localStorage.setItem('mySubmissions', JSON.stringify(mySubmissions));
				}

				// Redirect to queue page with submission highlighted
				await goto(`/queue?highlight=${result.submissionId}`);
			} else {
				submitSuccess = true;
				prompt = '';
				email = '';
			}

		} catch (error) {
			submitError = error instanceof Error ? error.message : 'An error occurred';
		} finally {
			isSubmitting = false;
		}
	}
</script>

<svelte:head>
	<title>Submit a Request - Claude Draws</title>
	<meta
		name="description"
		content="Submit your Kid Pix artwork request to Claude Draws. Describe your vision and watch Claude bring it to life!"
	/>
</svelte:head>

<div class="min-h-screen">
	<Header />

	<!-- Navigation/Back Button Bar -->
	<nav class="bg-kidpix-purple border-b-4 border-black p-4">
		<div class="container mx-auto flex justify-between items-center">
			<a
				href="/"
				class="bg-kidpix-yellow text-black font-bold text-lg px-4 py-2 border-4 border-black shadow-chunky hover:shadow-chunky-hover hover:translate-x-1 hover:translate-y-1 active:translate-x-2 active:translate-y-2 active:shadow-none uppercase transition-all"
			>
				← Back
			</a>
			<p class="text-white font-bold text-xl text-center uppercase hidden sm:block">
				Submit Your Request
			</p>
		</div>
	</nav>

	<!-- Main Content -->
	<main class="container mx-auto p-4 sm:p-8">
		<div class="max-w-3xl mx-auto">
			<!-- Success Message -->
			{#if submitSuccess}
				<div class="bg-kidpix-green border-4 border-black p-6 shadow-chunky-lg mb-8 animate-stamp">
					<h2 class="text-2xl font-black uppercase mb-4">Success!</h2>
					<p class="text-lg font-bold mb-4">
						Your request has been submitted! Claude Draws will get to work on it soon.
					</p>
					<p class="text-lg font-bold mb-4">
						{#if email}
							You'll receive an email at <strong>{email}</strong> when your artwork is complete.
						{:else}
							Check back at the <a href="/gallery">gallery</a> to see your completed artwork!
						{/if}
					</p>
					<button
						on:click={() => submitSuccess = false}
						class="bg-kidpix-yellow text-black font-bold text-lg px-6 py-3 border-4 border-black shadow-chunky hover:shadow-chunky-hover hover:translate-x-1 hover:translate-y-1 active:translate-x-2 active:translate-y-2 active:shadow-none uppercase transition-all"
					>
						Submit Another
					</button>
				</div>
			{/if}

			<!-- Introduction -->
			<div class="bg-kidpix-cyan border-4 border-black p-6 sm:p-8 shadow-chunky-lg mb-8">
				<h1 class="text-3xl font-black uppercase mb-4 pb-4 border-b-4 border-black">
					Request an Artwork
				</h1>
				<div class="space-y-4 text-lg font-bold">
					<p>
						Describe the artwork you'd like Claude to create using Kid Pix! Be specific about what you want to see.
					</p>
					<p>
						Claude Draws will illustrate your request and add it to the gallery. You can optionally provide an email address for a notification when it's complete.
					</p>
					<p>
						Looking for inspiration? Check out the <a href="/gallery">gallery</a> to see what Claude Draws has created so far!
					</p>
				</div>
			</div>

			<!-- Submission Form -->
			<form on:submit={handleSubmit} class="bg-white border-4 border-black p-6 sm:p-8 shadow-chunky-lg">
				<!-- Prompt Field -->
				<div class="mb-6">
					<label for="prompt" class="block text-xl font-black uppercase mb-3">
						Your Request <span class="text-kidpix-red">*</span>
					</label>
					<textarea
						id="prompt"
						bind:value={prompt}
						required
						rows="6"
						placeholder="Example: Draw a sunset over mountains with a sailboat on a lake..."
						class="w-full px-4 py-3 border-4 border-black text-lg font-bold focus:outline-none focus:ring-4 focus:ring-kidpix-purple resize-none"
					></textarea>
					<p class="mt-2 text-sm font-bold text-gray-600">
						Be descriptive! The more detail you provide, the better Claude can bring your vision to life.
					</p>
				</div>

				<!-- Email Field (Optional) -->
				<div class="mb-6">
					<label for="email" class="block text-xl font-black uppercase mb-3">
						Email (Optional)
					</label>
					<input
						id="email"
						type="email"
						bind:value={email}
						placeholder="your@email.com"
						class="w-full px-4 py-3 border-4 border-black text-lg font-bold focus:outline-none focus:ring-4 focus:ring-kidpix-purple"
					/>
					<p class="mt-2 text-sm font-bold text-gray-600">
						Get notified when your artwork is complete! Your email will not be shared or used for any other purpose.
					</p>
				</div>

				<!-- Error Message -->
				{#if submitError}
					<div class="bg-kidpix-red border-4 border-black p-4 mb-6">
						<p class="text-white font-black uppercase">Error: {submitError}</p>
					</div>
				{/if}

				<!-- Submit Button -->
				<button
					type="submit"
					disabled={isSubmitting || !prompt.trim()}
					class="w-full bg-kidpix-purple text-white font-black text-2xl px-8 py-4 border-4 border-black shadow-chunky-lg hover:shadow-chunky-hover hover:translate-x-1 hover:translate-y-1 active:translate-x-2 active:translate-y-2 active:shadow-none uppercase transition-all disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:translate-x-0 disabled:hover:translate-y-0 disabled:hover:shadow-chunky-lg"
				>
					{isSubmitting ? 'Submitting...' : 'Submit Request'}
				</button>
			</form>
		</div>
	</main>

	<Footer />
</div>
