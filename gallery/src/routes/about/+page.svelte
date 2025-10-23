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
						Is AI ready for the <a href="https://www.youtube.com/watch?v=QSco7JoMqyI">Information Superhighway</a>?
					</p>
					<p>
						Hi, I'm <a href="https://andrewtorkbaker.com/">Andrew</a>. I'm a software engineer.
					</p>
					<p>
						I first posed the question above in a newsletter I write about AI. That issue was all about browser agents - AI that uses websites like you and I do. It's a topic that's getting increased attention these days. Just about every big AI lab now has a browser agent project, and there are new ones all the time. OpenAI released their <a href="https://openai.com/index/introducing-chatgpt-atlas/">ChatGPT Atlas</a> browser just a few days ago!
					</p>
					<p>
						Nobody calls the internet "the information superhighway" today. I mentioned it in my newsletter as a throwaway joke. But it got me thinking about my own early experiences with computers and the internet in the 1990s. And when I think about those special afternoons in my school's computer lab, one piece of software made a bigger impact on me than any other: Kid Pix.
					</p>
					<p>
						Craig Hickman started working on Kid Pix in 1988. At the time he was a photographer, not a professional engineer. But when Craig saw his 3-year-old son struggle to use MacPaint, he was inspired to create a kid-friendly graphic design application. If you were a Kid Pix kid like me, you'll enjoy reading <a href="http://red-green-blue.com/kid-pix-the-early-years">Craig's short history of Kid Pix's early years</a> on his site.
					</p>
					<p>
						What made Kid Pix great was that it was easy to use, open ended, and full of surprises. I spent hours exploring every tool and stamp sheet. What was rewarding about those hours wasn't my glorious finished artwork, however. Kid Pix occupies a special place in my heart because it gave me my first digital sandbox to build, break, and build again. That sparked an interest in computers that's been a big part of my life ever since.
					</p>
					<p>
						Fast forward to today. Like many engineers, I spend a lot of time experimenting with AI to discover what it can do well and what it can't. As these latest AI tools take their first steps towards using computers like we do, I wondered: could they use Kid Pix like I did?
					</p>
					<p>
						Anthropic began onboarding users to its <a href="https://www.anthropic.com/news/claude-for-chrome">Claude for Chrome</a> research preview this summer. This flavor of browser agent is powered by Anthropic's servers in the cloud, but runs on your computer as a browser extension. You can see everything Claude does while it works, and stop it at any time.
					</p>
					<p>
						Last year <a href="https://github.com/vikrum/kidpix">Vikrum Nijjar reimplemented Kid Pix v1.0</a> using modern HTML, CSS, and JavaScript. I pointed Claude for Chrome at <a href="https://kidpix.app/">https://kidpix.app</a> and was pretty impressed with the results. The finished output was closer to my vision than I had expected, and it was a lot of fun watching Claude think through its design. Suddenly, I was spending hours lost in Kid Pix all over again.
					</p>
					<p>
						I decided to share this delightful experience more broadly so anybody can try it and learn a bit about AI browser agents. And so Claude Draws was born.
					</p>
					<p>
						Here's how it works:
					</p>
					<p>
						- Think up a drawing you would like Claude Draws to illustrate for you using Kid Pix
					</p>
					<p>
						- Go to the <a href="https://www.reddit.com/r/ClaudeDraws/">r/ClaudeDraws</a> subreddit and create a new post describing your design. Don't forget to use the "Open request" flair on your new post!
					</p>
					<p>
						- Open up the livestream and watch Claude Draws get to work on your design
					</p>
					<p>
						Claude Draws works through the queue of outstanding requests in descending order of the post's upvote count. So depending on the length of the queue, it might take a while for Claude Draws to get to your submission. But don't worry, you don't need to watch the livestream 24/7 to see your artwork - Claude Draws will leave a comment on your Reddit post when it finishes.
					</p>
					<p>
						You can find me online on <a href="https://x.com/andrewtorkbaker">Twitter</a> and <a href="https://www.linkedin.com/in/andrewtorkbaker/">LinkedIn</a>. You can subscribe to my newsletter about AI <a href="https://implausible.ai/blog/">here</a>. I'm planning to author a more detailed technical post about this project sometime soon.
					</p>
					<p>
						Special thanks to <a href="https://github.com/vikrum">Vikrum Nijjar</a> for his excellent Kid Pix port, the <a href="https://sf.aitinkerers.org/">SF AI Tinkerers</a> community for their feedback after my Claude Draws demo last week, and Craig Hickman for creating software which no doubt inspired a generation of artists, designers, and engineers.
					</p>
				</div>
			</div>

			<!-- FAQ Section -->
			<div class="bg-white border-4 border-black p-6 sm:p-8 shadow-chunky-lg">
				<h2 class="text-3xl font-black uppercase mb-6 pb-4 border-b-4 border-black">
					Frequently Asked Questions
				</h2>
				<div class="space-y-4">
					<!-- FAQ 1 -->
					<details class="group bg-kidpix-pink border-4 border-black p-4 shadow-chunky">
						<summary
							class="text-lg font-black uppercase cursor-pointer hover:text-black list-none flex items-center gap-2"
						>
							<span class="transform transition-transform group-open:rotate-90 text-2xl"
								>▶</span
							>
							Wait… this Kid Pix looks a little different than I remember!
						</summary>
						<div class="mt-4 text-base font-bold leading-relaxed space-y-4">
							<p>
								Good eye! Vikrum's Kid Pix implementation is pretty faithful to the original - <a href="https://kidpix.app/">you can use it here</a>. I <a href="https://github.com/atbaker/kidpix/">forked that repo</a> and made a few changes to help Claude (and other browser agents) use Kid Pix more easily.
							</p>
							<p>
								Some of those changes were necessary because of Claude for Chrome's limitations. For example: it can't emulate a "shift + click", necessary to create enlarged versions of Kid Pix stamps. So I added a toggle it can use to hold down a virtual "shift" key instead.
							</p>
							<p>
								Other changes, though, just help Claude stay on track. Browser agents work best when they can use a combination of screenshot and HTML data, and when that HTML data has useful information included in each element. My fork adds a lot of little details to the HTML to help Claude understand what will happen when it presses each individual button.
							</p>
							<p>
								Finally, I added a status bar so Claude and livestream viewers alike can more easily see what tools and subtools are active at any given moment.
							</p>
							<p>
								If you are a Kid Pix purist, you can find <a href="https://archive.org/details/kid-pix-11">a full emulator loaded with v1.1</a> on the Wayback Machine.
							</p>
						</div>
					</details>

					<!-- FAQ 2 -->
					<details class="group bg-kidpix-pink border-4 border-black p-4 shadow-chunky">
						<summary
							class="text-lg font-black uppercase cursor-pointer hover:text-black list-none flex items-center gap-2"
						>
							<span class="transform transition-transform group-open:rotate-90 text-2xl"
								>▶</span
							>
							Is Claude Draws open source?
						</summary>
						<div class="mt-4 text-base font-bold leading-relaxed space-y-4">
							<p>
								Yes, Claude Draws is open source under the MIT license. You can find the GitHub repo <a href="https://github.com/atbaker/claude-draws">here</a>.
							</p>
							<p>
								I don't recommend trying to set up the repo yourself just yet. The docs will get a bit more love this weekend. If you're itching to try anyway, you're welcome to open an issue if you get stuck.
							</p>
						</div>
					</details>

					<!-- FAQ 3 -->
					<details class="group bg-kidpix-pink border-4 border-black p-4 shadow-chunky">
						<summary
							class="text-lg font-black uppercase cursor-pointer hover:text-black list-none flex items-center gap-2"
						>
							<span class="transform transition-transform group-open:rotate-90 text-2xl"
								>▶</span
							>
							What tools did you use to build this?
						</summary>
						<div class="mt-4 text-base font-bold leading-relaxed space-y-4">
							<p>
								Anthropic's Claude for Chrome browser extension does the heavy lifting here. Most of the Claude Draws code is focused on sourcing requests from Reddit, programmatically injecting prompts into the browser extension, and then post-processing the newly created artwork before adding it to the gallery site.
							</p>
							<p>
								I wrote most of that code in Python using Cursor and Claude Code. The other notable tools in this project are <a href="https://github.com/microsoft/playwright-python">Playwright</a>, <a href="https://github.com/temporalio/temporal">Temporal</a>, and <a href="https://github.com/boundaryml/baml">BAML</a>.
							</p>
						</div>
					</details>
				</div>
			</div>
		</div>
	</main>

	<Footer />
</div>
