<script lang="ts">
	let { videoUrl }: { videoUrl: string } = $props();
</script>

<div class="video-player border-4 border-black bg-black">
	<video
		class="w-full h-auto"
		controls
		preload="metadata"
	>
		<source src={videoUrl} type="video/mp4" />
		<track kind="captions" />
		Your browser does not support the video tag.
	</video>
</div>

<style>
	.video-player video {
		display: block;
	}
</style>
