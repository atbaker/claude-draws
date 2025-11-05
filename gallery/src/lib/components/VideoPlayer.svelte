<script lang="ts">
	import { onMount } from 'svelte';

	let { videoUrl }: { videoUrl: string } = $props();

	let videoElement: HTMLVideoElement;
	let isPlaying = $state(false);
	let currentTime = $state(0);
	let duration = $state(0);
	let volume = $state(1);
	let isMuted = $state(false);
	let isFullscreen = $state(false);

	function togglePlay() {
		if (videoElement.paused) {
			videoElement.play();
			isPlaying = true;
		} else {
			videoElement.pause();
			isPlaying = false;
		}
	}

	function handleTimeUpdate() {
		currentTime = videoElement.currentTime;
	}

	function handleLoadedMetadata() {
		duration = videoElement.duration;
	}

	function handleEnded() {
		isPlaying = false;
	}

	function seek(event: MouseEvent) {
		const progressBar = event.currentTarget as HTMLElement;
		const rect = progressBar.getBoundingClientRect();
		const pos = (event.clientX - rect.left) / rect.width;
		videoElement.currentTime = pos * duration;
	}

	function toggleMute() {
		isMuted = !isMuted;
		videoElement.muted = isMuted;
	}

	function changeVolume(event: Event) {
		const target = event.target as HTMLInputElement;
		volume = parseFloat(target.value);
		videoElement.volume = volume;
		if (volume === 0) {
			isMuted = true;
		} else if (isMuted) {
			isMuted = false;
			videoElement.muted = false;
		}
	}

	function toggleFullscreen() {
		if (!document.fullscreenElement) {
			videoElement.requestFullscreen();
			isFullscreen = true;
		} else {
			document.exitFullscreen();
			isFullscreen = false;
		}
	}

	function formatTime(seconds: number): string {
		const mins = Math.floor(seconds / 60);
		const secs = Math.floor(seconds % 60);
		return `${mins}:${secs.toString().padStart(2, '0')}`;
	}

	onMount(() => {
		const handleFullscreenChange = () => {
			isFullscreen = !!document.fullscreenElement;
		};
		document.addEventListener('fullscreenchange', handleFullscreenChange);
		return () => {
			document.removeEventListener('fullscreenchange', handleFullscreenChange);
		};
	});
</script>

<div class="video-player bg-black border-4 border-black">
	<video
		bind:this={videoElement}
		class="w-full h-auto"
		src={videoUrl}
		ontimeupdate={handleTimeUpdate}
		onloadedmetadata={handleLoadedMetadata}
		onended={handleEnded}
		onplay={() => (isPlaying = true)}
		onpause={() => (isPlaying = false)}
	>
		<track kind="captions" />
	</video>

	<!-- Custom Controls -->
	<div class="bg-kidpix-cyan border-t-4 border-black p-3 space-y-2">
		<!-- Progress Bar -->
		<div class="relative">
			<button
				class="w-full h-6 bg-white border-4 border-black cursor-pointer overflow-hidden"
				onclick={seek}
				aria-label="Seek video"
			>
				<div
					class="h-full bg-kidpix-purple transition-all duration-100"
					style="width: {duration > 0 ? (currentTime / duration) * 100 : 0}%"
				></div>
			</button>
			<div class="flex justify-between mt-1 text-xs font-bold">
				<span>{formatTime(currentTime)}</span>
				<span>{formatTime(duration)}</span>
			</div>
		</div>

		<!-- Control Buttons -->
		<div class="flex items-center gap-2 flex-wrap">
			<!-- Play/Pause Button -->
			<button
				class="bg-{isPlaying
					? 'kidpix-yellow'
					: 'kidpix-green'} text-black font-black text-sm px-4 py-2 border-4 border-black shadow-chunky hover:shadow-chunky-hover hover:translate-x-1 hover:translate-y-1 active:translate-x-2 active:translate-y-2 active:shadow-none uppercase transition-all"
				onclick={togglePlay}
			>
				{isPlaying ? '⏸ Pause' : '▶ Play'}
			</button>

			<!-- Volume Controls -->
			<div class="flex items-center gap-2 bg-white border-4 border-black p-2 flex-1 min-w-[200px]">
				<button
					class="bg-kidpix-blue text-white font-black text-xs px-2 py-1 border-2 border-black uppercase"
					onclick={toggleMute}
					aria-label={isMuted ? 'Unmute' : 'Mute'}
				>
					{isMuted ? '🔇' : '🔊'}
				</button>
				<input
					type="range"
					min="0"
					max="1"
					step="0.1"
					value={volume}
					oninput={changeVolume}
					class="flex-1 h-2 accent-kidpix-blue"
					aria-label="Volume"
				/>
			</div>

			<!-- Fullscreen Button -->
			<button
				class="bg-kidpix-orange text-black font-black text-sm px-4 py-2 border-4 border-black shadow-chunky hover:shadow-chunky-hover hover:translate-x-1 hover:translate-y-1 active:translate-x-2 active:translate-y-2 active:shadow-none uppercase transition-all"
				onclick={toggleFullscreen}
			>
				{isFullscreen ? '⊠ Exit' : '⊡ Full'}
			</button>
		</div>
	</div>
</div>

<style>
	.video-player video {
		display: block;
	}
</style>
