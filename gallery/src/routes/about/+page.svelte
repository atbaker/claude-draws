<script lang="ts">
	import Header from '$lib/components/Header.svelte';
	import Footer from '$lib/components/Footer.svelte';
</script>

<svelte:head>
	<title>About - Claude Draws</title>
	<meta
		name="description"
		content="Learn about Claude Draws, an AI art project by Andrew Tork Baker"
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
				About This Project
			</p>
		</div>
	</nav>

	<!-- Main Content -->
	<main class="container mx-auto p-4 sm:p-8">
		<div class="max-w-4xl mx-auto">
			<!-- Hero Image -->
			<div class="bg-kidpix-cyan border-4 border-black shadow-chunky-lg mb-8">
				<div class="bg-white border-b-4 border-black p-4 sm:p-8">
					<div class="border-4 border-black bg-gray-100 p-2 aspect-[4/3]">
						<img
							src="/about-hero.jpg"
							alt="Featured Claude Draws artwork"
							class="w-full h-full object-contain"
						/>
					</div>
				</div>
			</div>

			<!-- About Section -->
			<div class="bg-kidpix-yellow border-4 border-black p-6 sm:p-8 shadow-chunky-lg mb-8">
				<h2 class="text-3xl font-black uppercase mb-6 pb-4 border-b-4 border-black">
					About the Project
				</h2>
				<div class="space-y-4 text-lg font-bold leading-relaxed">
					<p>
						Lorem ipsum dolor sit amet, <a href="https://www.google.com">google</a> consectetur adipiscing elit. Sed do eiusmod tempor
						incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud
						exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat.
					</p>
					<p>
						Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore eu
						fugiat nulla pariatur. Excepteur sint occaecat cupidatat non proident, sunt in culpa
						qui officia deserunt mollit anim id est laborum.
					</p>
					<p>
						Sed ut perspiciatis unde omnis iste natus error sit voluptatem accusantium doloremque
						laudantium, totam rem aperiam, eaque ipsa quae ab illo inventore veritatis et quasi
						architecto beatae vitae dicta sunt explicabo.
					</p>
				</div>
			</div>

			<!-- FAQ Section -->
			<div class="bg-white border-4 border-black p-6 sm:p-8 shadow-chunky-lg">
				<h2 class="text-3xl font-black uppercase mb-6 pb-4 border-b-4 border-black">
					Frequently Asked Questions
				</h2>
				<div class="space-y-4">
					{#each Array(7) as _, i}
						<details class="group bg-kidpix-pink border-4 border-black p-4 shadow-chunky">
							<summary
								class="text-lg font-black uppercase cursor-pointer hover:text-black list-none flex items-center gap-2"
							>
								<span class="transform transition-transform group-open:rotate-90 text-2xl"
									>▶</span
								>
								Question {i + 1}: Placeholder FAQ question here?
							</summary>
							<div class="mt-4 text-base font-bold leading-relaxed">
								<p>
									This is a placeholder answer. Lorem ipsum dolor sit amet, consectetur
									adipiscing elit. Sed do eiusmod tempor incididunt ut labore et dolore magna
									aliqua.
								</p>
							</div>
						</details>
					{/each}
				</div>
			</div>
		</div>
	</main>

	<Footer />
</div>
