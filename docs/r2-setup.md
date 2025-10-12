# Cloudflare R2 Setup Guide

This guide walks through setting up Cloudflare R2 storage for the Claude Draws gallery.

## Prerequisites

- A Cloudflare account (free tier is sufficient)
- The domain `claudedraws.com` added to your Cloudflare account
- An R2 bucket named `claudedraws-dev` (already created)

## Step 1: Configure R2 API Credentials

1. Go to the [Cloudflare Dashboard](https://dash.cloudflare.com/)
2. Navigate to **R2** in the left sidebar
3. Click **Manage R2 API Tokens** (top right)
4. Click **Create API Token**
5. Configure the token:
   - **Token name**: `claude-draws-gallery-dev`
   - **Permissions**: Select "Object Read & Write"
   - **Specify buckets** (optional): Select `claudedraws-dev` to restrict access
6. Click **Create API Token**
7. Copy the credentials shown:
   - **Access Key ID**
   - **Secret Access Key**
   - **Account ID** (also visible in URL: `https://dash.cloudflare.com/<ACCOUNT_ID>/r2/...`)

8. Add these to your `.env` file:
   ```bash
   R2_ACCOUNT_ID=<your_account_id>
   R2_ACCESS_KEY_ID=<your_access_key_id>
   R2_SECRET_ACCESS_KEY=<your_secret_access_key>
   R2_BUCKET_NAME=claudedraws-dev
   ```

⚠️ **Important**: Save these credentials securely! The secret access key is only shown once.

## Step 2: Enable Public Access on R2 Bucket

By default, R2 buckets are private. To make artwork publicly accessible, you need to configure public access.

### Option A: Custom Domain (Recommended)

Using a custom domain provides clean URLs and better control.

1. In the Cloudflare Dashboard, go to **R2** → **Buckets**
2. Click on your `claudedraws-dev` bucket
3. Go to the **Settings** tab
4. Under **Public Access**, click **Connect Domain**
5. Choose **Custom Domain**
6. Enter your subdomain: `r2.claudedraws.com`
7. Click **Connect Domain**
8. Cloudflare will automatically create a DNS record

Your artwork will now be accessible at:
```
https://r2.claudedraws.com/kidpix-1234567890.png
https://r2.claudedraws.com/kidpix-1234567890.json
```

Update your `.env`:
```bash
R2_PUBLIC_URL=https://r2.claudedraws.com
```

### Option B: r2.dev Subdomain (Simpler, but less control)

If you prefer not to use a custom domain:

1. In bucket settings, under **Public Access**, click **Allow Access**
2. Copy the auto-generated `r2.dev` URL (e.g., `https://pub-abc123.r2.dev`)
3. Update your `.env`:
   ```bash
   R2_PUBLIC_URL=https://pub-abc123.r2.dev
   ```

⚠️ **Note**: `r2.dev` URLs are subject to Cloudflare's rate limits and may not be suitable for high-traffic sites.

## Step 3: Configure CORS (Optional)

If your gallery site will fetch data from R2 via JavaScript (unlikely with static site generation), you may need to configure CORS.

1. In bucket settings, go to **CORS Policy**
2. Add the following policy:
   ```json
   [
     {
       "AllowedOrigins": ["https://claudedraws.com"],
       "AllowedMethods": ["GET", "HEAD"],
       "AllowedHeaders": ["*"],
       "ExposeHeaders": ["ETag"],
       "MaxAgeSeconds": 3600
     }
   ]
   ```

## Step 4: Verify Setup

Test your R2 configuration using the build script:

```bash
# Test upload (creates a test artwork in R2)
./scripts/build_gallery.py --test-upload ./downloads/kidpix-test.png \
  --title "Test Artwork" \
  --reddit-url "https://reddit.com/r/test/comments/123456"

# The script will print public URLs - verify they're accessible
```

If successful, you should see output like:
```
✓ Test upload complete!
  Artwork ID: kidpix-1710501234
  Image URL: https://r2.claudedraws.com/kidpix-1710501234.png
  Metadata URL: https://r2.claudedraws.com/kidpix-1710501234.json
```

Open the image URL in your browser to confirm public access is working.

## Step 5: Test Build Script

```bash
# Full rebuild (generates gallery-metadata.json from R2)
./scripts/build_gallery.py --full

# Verify the generated file
cat gallery-metadata.json
```

You should see a JSON file with your test artwork:
```json
{
  "artworks": [
    {
      "id": "kidpix-1710501234",
      "imageUrl": "https://r2.claudedraws.com/kidpix-1710501234.png",
      "title": "Test Artwork",
      "redditPostUrl": "https://reddit.com/r/test/comments/123456",
      "createdAt": "2024-03-15T10:20:34.567890+00:00",
      "videoUrl": null
    }
  ],
  "lastUpdated": "2024-03-15T10:21:00.123456+00:00"
}
```

## Troubleshooting

### Error: "Missing required environment variables"

Make sure your `.env` file exists and contains all required variables:
```bash
cat .env
```

If variables are missing, copy from `.env.example` and fill in your values.

### Error: "Access Denied" or "403 Forbidden"

**Possible causes:**
1. API token doesn't have correct permissions (needs "Object Read & Write")
2. API token is restricted to different buckets
3. Credentials are incorrect

**Fix:** Generate a new API token with correct permissions.

### Error: "NoSuchBucket"

The bucket name in your `.env` doesn't match the actual bucket.

**Fix:** Verify bucket name in Cloudflare Dashboard and update `.env`:
```bash
R2_BUCKET_NAME=claudedraws-dev
```

### Public URLs return 404

**Possible causes:**
1. Public access not enabled on bucket
2. Custom domain not connected properly
3. File doesn't exist in R2

**Fix:**
1. Check bucket settings → Public Access
2. Verify custom domain DNS record exists
3. List bucket contents:
   ```bash
   # Add debug code to build_gallery.py to list objects
   ```

### CORS errors in browser console

If your static site tries to fetch data from R2 via JavaScript and you see CORS errors:

**Fix:** Add CORS policy (see Step 3 above)

## Cost Estimation

Cloudflare R2 pricing (as of 2024):

- **Storage**: $0.015/GB/month
- **Class A operations** (writes): $4.50 per million requests
- **Class B operations** (reads): $0.36 per million requests
- **Egress**: **FREE** (this is R2's main advantage over S3!)

**Estimated costs for Claude Draws:**

Assuming:
- 100 artworks/day (very busy!)
- 800KB average file size
- 10,000 page views/day

Monthly costs:
- Storage: ~2.4GB = $0.04
- Writes: ~6,000 requests = $0.03
- Reads: ~300,000 requests = $0.11

**Total: ~$0.18/month** 🎉

Even with 10x traffic, costs remain negligible. Egress is free, so viral Reddit posts won't bankrupt you!

## Next Steps

Once R2 is configured:

1. ✅ R2 bucket created and configured
2. ✅ API credentials added to `.env`
3. ✅ Public access enabled
4. ✅ Build script tested

You're ready to move to **Phase 2**: Building the SvelteKit gallery site!

See [gallery-architecture.md](./gallery-architecture.md) for next steps.
