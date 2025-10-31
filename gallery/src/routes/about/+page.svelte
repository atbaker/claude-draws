<script lang="ts">
	import Header from '$lib/components/Header.svelte';
	import Footer from '$lib/components/Footer.svelte';
</script>

<svelte:head>
	<title>About - Claude Draws</title>
	<meta
		name="description"
		content="Is AI ready for the Information Superhighway? Learn about Claude Draws, an interactive educational demo exploring AI browser agents through Kid Pix art."
	/>

	<!-- Open Graph / Facebook -->
	<meta property="og:type" content="website" />
	<meta property="og:url" content="https://claudedraws.com/about" />
	<meta property="og:title" content="About - Claude Draws" />
	<meta property="og:description" content="Is AI ready for the Information Superhighway? Learn about Claude Draws, an interactive educational demo exploring AI browser agents through Kid Pix art." />
	<meta property="og:image" content="https://claudedraws.com/about-hero.jpg" />

	<!-- Twitter -->
	<meta property="twitter:card" content="summary_large_image" />
	<meta property="twitter:url" content="https://claudedraws.com/about" />
	<meta property="twitter:title" content="About - Claude Draws" />
	<meta property="twitter:description" content="Is AI ready for the Information Superhighway? Learn about Claude Draws, an interactive educational demo exploring AI browser agents through Kid Pix art." />
	<meta property="twitter:image" content="https://claudedraws.com/about-hero.jpg" />
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
						I first posed that question in <a href="https://implausible.ai/blog/the-state-of-browser-ai-agents/">a newsletter I write about AI</a>. That issue was all about browser agents - AI that uses websites like you and I do. It's a topic that's getting increased attention these days. Just about every big AI lab now has a browser agent project, and there are new ones all the time. OpenAI released their <a href="https://openai.com/index/introducing-chatgpt-atlas/">ChatGPT Atlas</a> browser just a few weeks ago!
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
						- Head over to the <a href="/submit">submission form</a> and describe your design in as much detail as you'd like. You can also optionally include your email address to get notified when it's done!
					</p>
					<p>
						- Open up the livestream and watch Claude Draws get to work on your design
					</p>
					<p>
						Claude Draws works through the queue by processing the most-upvoted submissions first. After you submit, you can check out the <a href="/queue">queue</a> to upvote other submissions - and others can upvote yours too! So depending on the length of the queue and how many upvotes your submission gets, it might take a while for Claude Draws to get to your submission. But don't worry, you don't need to watch the livestream 24/7 to see your artwork - if you included your email, Claude Draws will send you a notification when it finishes. Otherwise, you can check back in the gallery!
					</p>
					<p>
						You can find me online on <a href="https://x.com/andrewtorkbaker">Twitter</a> and <a href="https://www.linkedin.com/in/andrewtorkbaker/">LinkedIn</a>. You can subscribe to my newsletter about AI <a href="https://implausible.ai/blog/">here</a>. I'm planning to author a more detailed technical post about this project sometime soon.
					</p>
					<p>
						Special thanks to <a href="https://github.com/vikrum">Vikrum Nijjar</a> for his excellent Kid Pix port, the <a href="https://sf.aitinkerers.org/">SF AI Tinkerers</a> community for their feedback after my Claude Draws demo last week, and Craig Hickman for creating software which no doubt inspired a generation of artists, designers, and engineers.
					</p>
				</div>
			</div>
		</div>
	</main>

	<Footer />
</div>
