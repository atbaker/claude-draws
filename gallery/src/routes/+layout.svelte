<script lang="ts">
	import '../app.css';

	let { children } = $props();
</script>

<svelte:head>
	<link rel="icon" href="/favicon.ico" sizes="any" />
	<link rel="icon" href="/favicon-16x16.png" type="image/png" sizes="16x16" />
	<link rel="icon" href="/favicon-32x32.png" type="image/png" sizes="32x32" />
	<link rel="apple-touch-icon" href="/apple-touch-icon.png" />
	<link rel="manifest" href="/site.webmanifest" />

	<!-- Privacy-friendly analytics by Plausible -->
	<script async src="https://plausible.io/js/pa-QhDTxJrWUXdIB3bKcIGMp.js"></script>
	<script>
		window.plausible=window.plausible||function(){(plausible.q=plausible.q||[]).push(arguments)},plausible.init=plausible.init||function(i){plausible.o=i||{}};
		plausible.init()
	</script>
</svelte:head>

{@render children?.()}
