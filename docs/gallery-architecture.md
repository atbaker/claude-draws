# Gallery Architecture

## Overview

The Claude Draws gallery is a static website that displays artwork created by Claude for Chrome using Kid Pix. The gallery serves two primary purposes:

1. **Public display**: A beautiful, scalable website showcasing all Claude Draws artwork
2. **URL generation**: After each artwork is created, the gallery provides a public URL that Claude can post back to Reddit

### Key Design Principles

- **R2 as source of truth**: All artwork images and metadata are stored durably in Cloudflare R2
- **Static site generation**: Gallery is pre-rendered HTML/CSS/JS for maximum performance and scalability
- **Append-only builds**: Fast builds that append new artwork without querying R2
- **Temporal orchestration**: Reliable workflow handling upload, build, and deployment with automatic retries
- **No database**: Simple JSON-based metadata, no database to manage

## Architecture Components

```
┌─────────────────────────────────────────────────────────────┐
│                      Home PC (Docker)                        │
│                                                              │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐ │
│  │  claudedraw  │───▶│   Temporal   │───▶│   Temporal   │ │
│  │     CLI      │    │    Server    │    │    Worker    │ │
│  └──────────────┘    └──────────────┘    └──────────────┘ │
│                                                  │           │
└──────────────────────────────────────────────────┼──────────┘
                                                   │
                         ┌─────────────────────────┼─────────────────────────┐
                         │                         ▼                         │
                         │     ┌─────────────────────────────────┐          │
                         │     │     Cloudflare R2 Bucket        │          │
                         │     │                                 │          │
                         │     │  kidpix-1234.png                │          │
                         │     │  kidpix-1234.json (metadata)    │          │
                         │     │  kidpix-5678.png                │          │
                         │     │  kidpix-5678.json (metadata)    │          │
                         │     │  ...                            │          │
                         │     └─────────────────────────────────┘          │
                         │                         │                         │
                         │                         ▼                         │
                         │     ┌─────────────────────────────────┐          │
                         │     │    SvelteKit Build Process      │          │
                         │     │                                 │          │
                         │     │  Reads gallery-metadata.json    │          │
                         │     │  Generates static HTML/CSS/JS   │          │
                         │     └─────────────────────────────────┘          │
                         │                         │                         │
                         │                         ▼                         │
                         │     ┌─────────────────────────────────┐          │
                         │     │   Cloudflare Workers            │          │
                         │     │   (with Static Assets)          │          │
                         │     │                                 │          │
                         │     │  https://claudedraws.com        │          │
                         │     │  (Static site hosting)          │          │
                         │     └─────────────────────────────────┘          │
                         └───────────────────────────────────────────────────┘
```

## Storage Strategy

### Cloudflare R2 Bucket

**Structure:**
```
kidpix-1710501234.png          # Artwork image
kidpix-1710501234.json         # Artwork metadata
kidpix-1710501567.png
kidpix-1710501567.json
...
```

**Metadata JSON format** (`kidpix-{timestamp}.json`):
```json
{
  "id": "kidpix-1710501234",
  "title": "A Happy Sun Over Mountains",
  "redditPostUrl": "https://reddit.com/r/drawmethis/comments/abc123",
  "createdAt": "2024-03-15T10:20:34Z",
  "videoUrl": null
}
```

**Why R2?**
- S3-compatible API (easy to work with)
- **Zero egress fees** (critical for popular gallery)
- Fast CDN delivery
- Durable storage (11 9's durability)
- Simple pricing

### Local Gallery Metadata (Gitignored)

**File:** `gallery/src/lib/gallery-metadata.json` (gitignored)

**Structure:**
```json
{
  "artworks": [
    {
      "id": "kidpix-1710501234",
      "imageUrl": "https://r2.claudedraws.com/kidpix-1710501234.png",
      "title": "A Happy Sun Over Mountains",
      "redditPostUrl": "https://reddit.com/r/drawmethis/comments/abc123",
      "createdAt": "2024-03-15T10:20:34Z",
      "videoUrl": null
    },
    {
      "id": "kidpix-1710501567",
      "imageUrl": "https://r2.claudedraws.com/kidpix-1710501567.png",
      "title": "Robot Dancing in Space",
      "redditPostUrl": "https://reddit.com/r/drawmethis/comments/def456",
      "createdAt": "2024-03-15T10:25:67Z",
      "videoUrl": null
    }
  ],
  "lastUpdated": "2024-03-15T10:25:67Z"
}
```

**Purpose:**
- Fast builds: SvelteKit reads this file at build time instead of querying R2
- Append-only: New artworks appended without full R2 scan
- Recoverable: Can always regenerate from R2 if corrupted

## Temporal Workflow

### Process Artwork Workflow

**Triggered by:** Python CLI after Claude finishes drawing

**Input:**
- `image_path`: Path to downloaded PNG file
- `title`: Artwork title (from Claude)
- `reddit_url`: URL of Reddit post that inspired this artwork

**Output:**
- `gallery_url`: Public URL to view the artwork

**Activities:**

```python
@workflow.defn
class ProcessArtworkWorkflow:
    @workflow.run
    async def run(self, image_path: str, title: str, reddit_url: str) -> str:
        artwork_id = f"kidpix-{int(time.time())}"

        # Activity 1: Upload image to R2
        image_url = await workflow.execute_activity(
            upload_image_to_r2,
            args=[artwork_id, image_path],
            start_to_close_timeout=timedelta(minutes=2),
            retry_policy=RetryPolicy(
                maximum_attempts=3,
                backoff_coefficient=2.0,
            )
        )

        # Activity 2: Upload metadata JSON to R2
        metadata = {
            "id": artwork_id,
            "title": title,
            "redditPostUrl": reddit_url,
            "createdAt": datetime.utcnow().isoformat(),
            "videoUrl": None
        }
        await workflow.execute_activity(
            upload_metadata_to_r2,
            args=[artwork_id, metadata],
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(maximum_attempts=3)
        )

        # Activity 3: Append to local gallery-metadata.json
        await workflow.execute_activity(
            append_to_gallery_metadata,
            args=[artwork_id, image_url, metadata],
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(maximum_attempts=3)
        )

        # Activity 4: Rebuild static site (fast - just HTML generation)
        await workflow.execute_activity(
            rebuild_static_site,
            start_to_close_timeout=timedelta(minutes=2),
            retry_policy=RetryPolicy(maximum_attempts=2)
        )

        # Activity 5: Deploy to Cloudflare Workers
        gallery_url = await workflow.execute_activity(
            deploy_to_cloudflare,
            start_to_close_timeout=timedelta(minutes=3),
            retry_policy=RetryPolicy(maximum_attempts=3)
        )

        return f"{gallery_url}/artwork/{artwork_id}"
```

**Key benefits:**
- ✅ Automatic retries for network failures
- ✅ Visibility into each step via Temporal UI
- ✅ Resumable if worker crashes
- ✅ Easy to add new steps (e.g., video processing)

## Build Process

### Build Script: `scripts/build_gallery.py`

**Two modes:**

#### Fast Mode (Default) - Append Only

```bash
./scripts/build_gallery.py --append kidpix-1710501234
```

**What it does:**
1. Fetches metadata from R2 for the specified artwork
2. Appends to `gallery/src/lib/gallery-metadata.json`
3. Does NOT query R2 for other artworks (assumes existing entries are valid)

**Use case:** Every artwork creation (called by Temporal workflow)

**Speed:** ~2-5 seconds

#### Full Rebuild Mode

```bash
./scripts/build_gallery.py --full
```

**What it does:**
1. Lists all objects in R2 bucket
2. Downloads each `kidpix-*.json` metadata file
3. Regenerates `gallery/src/lib/gallery-metadata.json` from scratch
4. Sorts by creation date (newest first)

**Use case:**
- Recovery from corruption
- Periodic verification (daily cron job?)
- Manual fixes/updates

**Speed:** ~30-60 seconds (depends on artwork count)

### SvelteKit Build Process

```bash
cd gallery
npm run build
```

**What happens:**
1. SvelteKit reads `src/lib/gallery-metadata.json`
2. Pre-renders all pages:
   - `/` - Gallery grid view
   - `/artwork/[id]` - Individual artwork pages
3. Outputs pure static HTML/CSS/JS to `build/`
4. No runtime dependencies, no API calls

**Speed:** ~5-10 seconds

**Output:** `gallery/build/` directory ready for deployment

## Frontend: SvelteKit Static Site

### Technology Stack

- **Framework:** SvelteKit (with @sveltejs/adapter-cloudflare)
- **Styling:** Tailwind 4 CSS
- **Hosting:** Cloudflare Workers (with static assets)
- **Assets:** Served from Cloudflare R2 with CDN

### Routes

**`/` (Gallery Grid)**
- Shows all artworks in grid layout
- Image thumbnails (loaded from R2)
- Click to view detail page
- Newest artworks first

**`/artwork/[id]` (Artwork Detail)**
- Full-size image
- Title
- Link to Reddit post that inspired it
- Creation timestamp
- (Future) Video recording of creation process

### Data Loading

**`src/routes/+page.js`:**
```javascript
import galleryMetadata from '$lib/gallery-metadata.json';

export const prerender = true;

export function load() {
    return {
        artworks: galleryMetadata.artworks
    };
}
```

**Key points:**
- `prerender = true` enables static generation
- Data loaded at build time, not runtime
- Fast page loads, no API calls from browser

### Example Component

**`src/routes/+page.svelte`:**
```svelte
<script>
    export let data;
</script>

<h1>Claude Draws Gallery</h1>

<div class="gallery-grid">
    {#each data.artworks as artwork}
        <a href="/artwork/{artwork.id}" class="artwork-card">
            <img src={artwork.imageUrl} alt={artwork.title} />
            <h2>{artwork.title}</h2>
            <time>{new Date(artwork.createdAt).toLocaleDateString()}</time>
        </a>
    {/each}
</div>

<style>
    .gallery-grid {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
        gap: 2rem;
    }

    .artwork-card img {
        width: 100%;
        height: auto;
        image-rendering: pixelated;
    }
</style>
```

## Project Structure

```
claude-draws/
├── claudedraw/                      # Python CLI (existing)
│   ├── __init__.py
│   ├── __main__.py
│   └── browser.py
├── workflows/                       # Temporal workflows (new)
│   ├── __init__.py
│   ├── activities.py               # R2 upload, build, deploy activities
│   └── process_artwork.py          # Main workflow definition
├── worker/                          # Temporal worker (new)
│   └── main.py                     # Runs worker process
├── gallery/                         # SvelteKit static site (new)
│   ├── src/
│   │   ├── routes/
│   │   │   ├── +page.svelte        # Gallery grid
│   │   │   ├── +page.js            # Data loading
│   │   │   └── artwork/
│   │   │       └── [id]/
│   │   │           ├── +page.svelte
│   │   │           └── +page.js
│   │   ├── lib/
│   │   │   └── gallery-metadata.json  # Gitignored!
│   │   └── app.html
│   ├── static/
│   │   └── favicon.png
│   ├── svelte.config.js
│   ├── package.json
│   └── .gitignore
├── scripts/                         # Build scripts (new)
│   ├── build_gallery.py            # Handles --append and --full
│   └── deploy.py                   # Deploy to Cloudflare Workers
├── kidpix/                          # Kid Pix fork (existing)
│   └── ...
├── docker-compose.yml               # Temporal + Worker services
├── .gitignore                       # Add gallery-metadata.json
├── .env.example                     # R2 credentials template
└── README.md
```

## Deployment Flow

### Development

**Terminal 1: Start Temporal**
```bash
docker-compose up temporal
```

**Terminal 2: Start Temporal Worker**
```bash
docker-compose up worker
```

**Terminal 3: Run gallery dev server**
```bash
cd gallery
npm run dev
# Open http://localhost:5173
```

**Terminal 4: Test CLI**
```bash
uv run claudedraw start --cdp-url ws://... --prompt "Draw a happy sun"
```

### Production (Automated)

**After each artwork:**
1. Temporal workflow runs automatically
2. Uploads to R2
3. Appends to local JSON
4. Rebuilds SvelteKit site
5. Deploys to Cloudflare Workers
6. Returns gallery URL
7. Python script submits second prompt to Claude to post URL on Reddit

**Deployment command:**
```bash
cd gallery
npm run build
wrangler deploy
```

Note: With SvelteKit's Cloudflare adapter, deployment is configured in `svelte.config.js` and uses `wrangler deploy` directly.

### Periodic Full Rebuild (Optional)

**Cron job running daily:**
```bash
#!/bin/bash
cd /path/to/claude-draws
./scripts/build_gallery.py --full
cd gallery
npm run build
wrangler deploy
```

**Purpose:**
- Verify data integrity
- Pick up any manual R2 changes
- Refresh metadata

## Configuration

### Environment Variables

**`.env` (local development):**
```bash
# Cloudflare R2
R2_ACCOUNT_ID=your_account_id
R2_ACCESS_KEY_ID=your_access_key
R2_SECRET_ACCESS_KEY=your_secret_key
R2_BUCKET_NAME=claude-draws-artworks
R2_PUBLIC_URL=https://r2.claudedraws.com

# Cloudflare Workers
CF_ACCOUNT_ID=your_account_id
CF_API_TOKEN=your_api_token

# Temporal
TEMPORAL_HOST=localhost:7233
```

**Docker Compose secrets:**
- Mount `.env` file into worker container
- Or use Docker secrets for production

### Cloudflare Setup

**R2 Bucket:**
1. Create bucket: `claude-draws-artworks`
2. Enable public access (or use signed URLs)
3. Configure custom domain: `r2.claudedraws.com`
4. Generate API token with R2 read/write permissions

**Cloudflare Workers:**
1. Install Wrangler CLI: `npm install -g wrangler`
2. Authenticate: `wrangler login`
3. Configure custom domain in `wrangler.toml`:
   ```toml
   name = "claude-draws-gallery"
   routes = [
     { pattern = "claudedraws.com", custom_domain = true }
   ]
   ```
4. Deploy: `wrangler deploy`

## Implementation Checklist

### Phase 1: R2 Storage + Basic Build Script

- [ ] Set up Cloudflare R2 bucket
- [ ] Configure R2 public access and custom domain
- [ ] Create `scripts/build_gallery.py` with:
  - [ ] `--append` mode (append to local JSON)
  - [ ] `--full` mode (rebuild from R2)
- [ ] Test manual upload + metadata creation
- [ ] Verify R2 URLs are publicly accessible

### Phase 2: SvelteKit Gallery

- [ ] Initialize SvelteKit project in `gallery/`
- [ ] Install `@sveltejs/adapter-static`
- [ ] Create gallery grid route (`/`)
- [ ] Create artwork detail route (`/artwork/[id]`)
- [ ] Style with retro/Kid Pix aesthetic
- [ ] Test local development with sample data
- [ ] Build and verify static output

### Phase 3: Cloudflare Workers Deployment

- [ ] Install Wrangler CLI: `npm install -g wrangler`
- [ ] Authenticate: `wrangler login`
- [ ] Create `wrangler.toml` configuration
- [ ] Test manual deployment: `wrangler deploy`
- [ ] Configure custom domain (`claudedraws.com`)
- [ ] Verify production gallery loads correctly

### Phase 4: Temporal Workflow

- [ ] Set up Docker Compose with Temporal server
- [ ] Create `workflows/process_artwork.py`
- [ ] Implement activities in `workflows/activities.py`:
  - [ ] `upload_image_to_r2`
  - [ ] `upload_metadata_to_r2`
  - [ ] `append_to_gallery_metadata`
  - [ ] `rebuild_static_site`
  - [ ] `deploy_to_cloudflare`
- [ ] Create worker in `worker/main.py`
- [ ] Test workflow end-to-end with sample artwork

### Phase 5: CLI Integration

- [ ] Modify `claudedraw/browser.py` to:
  - [ ] Extract artwork title from Claude's response
  - [ ] Trigger Temporal workflow after artwork creation
  - [ ] Wait for workflow completion
  - [ ] Retrieve gallery URL
- [ ] Add second Claude prompt to post URL on Reddit
- [ ] Test full flow: Reddit prompt → artwork → gallery → Reddit comment

### Phase 6: Polish & Monitoring

- [ ] Add error handling and logging
- [ ] Set up Temporal UI monitoring
- [ ] Create periodic full rebuild cron job
- [ ] Add gallery features:
  - [ ] Search/filter
  - [ ] Pagination
  - [ ] Share buttons
- [ ] Performance optimization:
  - [ ] Image optimization
  - [ ] Lazy loading
  - [ ] CDN caching headers
- [ ] Set up analytics (Cloudflare Analytics)

## Future Enhancements

### Video Recording
- Record browser screen during artwork creation
- Upload video to R2 alongside image
- Embed video player on artwork detail page

### Interactive Features
- Voting/likes (via edge function?)
- Comments (via third-party service)
- Random artwork button
- Time-lapse view of creation process

### Metadata Enhancements
- Tags/categories (parsed from Reddit post)
- Color palette extraction
- Tools used during creation
- Drawing time elapsed

### Performance
- Image thumbnails (generate during upload)
- Progressive image loading
- Service worker for offline viewing
- Prefetch artwork detail pages

## Troubleshooting

### Gallery not updating after new artwork

**Check:**
1. Was Temporal workflow successful? (Check Temporal UI)
2. Was metadata appended to local JSON? (`cat gallery/src/lib/gallery-metadata.json`)
3. Did SvelteKit build complete? (Check build logs)
4. Was deployment successful? (Check Wrangler output)

**Fix:** Run full rebuild:
```bash
./scripts/build_gallery.py --full
cd gallery && npm run build
wrangler pages deploy build/
```

### Local JSON corrupted

**Fix:** Regenerate from R2:
```bash
./scripts/build_gallery.py --full
```

### R2 upload failures

**Check:**
- R2 credentials in `.env`
- Network connectivity
- R2 bucket permissions
- Temporal workflow retry logs

**Fix:** Temporal will automatically retry. If still failing, check Temporal UI for specific error.

### Build too slow

**If full builds are slow:**
- Optimize R2 list/read operations (use pagination)
- Cache metadata locally (already doing this!)
- Increase Temporal activity timeout

**If SvelteKit builds are slow:**
- Reduce image processing
- Use faster image optimization libraries
- Consider incremental builds

## Resources

- [Cloudflare R2 Documentation](https://developers.cloudflare.com/r2/)
- [Cloudflare Workers Documentation](https://developers.cloudflare.com/workers/)
- [Cloudflare Workers Static Assets](https://developers.cloudflare.com/workers/static-assets/)
- [SvelteKit Cloudflare Adapter](https://kit.svelte.dev/docs/adapter-cloudflare)
- [SvelteKit on Cloudflare Workers Guide](https://developers.cloudflare.com/workers/framework-guides/web-apps/svelte/)
- [Temporal Python SDK](https://docs.temporal.io/dev-guide/python)
- [Wrangler CLI](https://developers.cloudflare.com/workers/wrangler/)
