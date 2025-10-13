"""Temporal activities for Claude Draws artwork processing."""

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Tuple

import boto3
from botocore.exceptions import ClientError
from baml_client.sync_client import b
from dotenv import load_dotenv
from temporalio import activity

# Load environment variables
load_dotenv()

# R2 Configuration
R2_ACCOUNT_ID = os.getenv("R2_ACCOUNT_ID")
R2_ACCESS_KEY_ID = os.getenv("R2_ACCESS_KEY_ID")
R2_SECRET_ACCESS_KEY = os.getenv("R2_SECRET_ACCESS_KEY")
R2_BUCKET_NAME = os.getenv("R2_BUCKET_NAME")
R2_PUBLIC_URL = os.getenv("R2_PUBLIC_URL")

# Paths
PROJECT_ROOT = Path(__file__).parent.parent
GALLERY_DIR = PROJECT_ROOT / "gallery"
GALLERY_METADATA_PATH = GALLERY_DIR / "src" / "lib" / "gallery-metadata.json"


def get_r2_client():
    """Create and return an R2 client using boto3."""
    return boto3.client(
        "s3",
        endpoint_url=f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
        aws_access_key_id=R2_ACCESS_KEY_ID,
        aws_secret_access_key=R2_SECRET_ACCESS_KEY,
        region_name="auto",
    )


@activity.defn
async def extract_artwork_metadata(response_html: str) -> Tuple[str, str]:
    """
    Extract artwork title and artist statement from Claude's HTML response using BAML.

    Args:
        response_html: HTML content from Claude for Chrome's final response

    Returns:
        Tuple of (title, artist_statement)
    """
    activity.logger.info("Extracting artwork metadata with BAML...")

    try:
        # Call BAML function to extract structured metadata
        metadata = b.ExtractArtworkMetadata(response_html)

        activity.logger.info(f"✓ Extracted title: {metadata.title}")
        activity.logger.info(f"✓ Extracted artist statement ({len(metadata.artist_statement)} chars)")

        return (metadata.title, metadata.artist_statement)

    except Exception as e:
        activity.logger.error(f"✗ Error extracting metadata: {e}")
        # Return fallback values if extraction fails
        return ("Claude Draws Artwork", "Artwork created with Kid Pix")


@activity.defn
async def upload_image_to_r2(artwork_id: str, image_path: str) -> str:
    """
    Upload artwork image to R2.

    Args:
        artwork_id: Unique identifier for the artwork (e.g., kidpix-1234567890)
        image_path: Path to the PNG image file

    Returns:
        Public URL of the uploaded image
    """
    activity.logger.info(f"Uploading image for {artwork_id}")

    client = get_r2_client()
    image_path_obj = Path(image_path)

    if not image_path_obj.exists():
        raise FileNotFoundError(f"Image file not found: {image_path}")

    try:
        with open(image_path, "rb") as f:
            client.put_object(
                Bucket=R2_BUCKET_NAME,
                Key=f"{artwork_id}.png",
                Body=f,
                ContentType="image/png",
            )

        image_url = f"{R2_PUBLIC_URL}/{artwork_id}.png"
        activity.logger.info(f"✓ Uploaded image: {image_url}")
        return image_url

    except ClientError as e:
        activity.logger.error(f"✗ Error uploading image: {e}")
        raise


@activity.defn
async def upload_metadata_to_r2(artwork_id: str, metadata: Dict) -> None:
    """
    Upload artwork metadata JSON to R2.

    Args:
        artwork_id: Unique identifier for the artwork
        metadata: Dictionary containing artwork metadata
    """
    activity.logger.info(f"Uploading metadata for {artwork_id}")

    client = get_r2_client()

    try:
        client.put_object(
            Bucket=R2_BUCKET_NAME,
            Key=f"{artwork_id}.json",
            Body=json.dumps(metadata, indent=2),
            ContentType="application/json",
        )

        activity.logger.info(f"✓ Uploaded metadata: {artwork_id}.json")

    except ClientError as e:
        activity.logger.error(f"✗ Error uploading metadata: {e}")
        raise


@activity.defn
async def append_to_gallery_metadata(artwork_id: str, image_url: str, metadata: Dict) -> None:
    """
    Append new artwork to local gallery metadata file.

    Args:
        artwork_id: Unique identifier for the artwork
        image_url: Public URL of the artwork image
        metadata: Dictionary containing artwork metadata
    """
    activity.logger.info(f"Appending {artwork_id} to gallery metadata")

    # Ensure directory exists
    GALLERY_METADATA_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Load existing gallery metadata or create new
    if GALLERY_METADATA_PATH.exists():
        with open(GALLERY_METADATA_PATH, "r") as f:
            gallery_metadata = json.load(f)
    else:
        gallery_metadata = {"artworks": [], "lastUpdated": None}

    # Check if artwork already exists
    existing_ids = {artwork["id"] for artwork in gallery_metadata["artworks"]}
    if artwork_id in existing_ids:
        activity.logger.warning(f"⚠ Artwork {artwork_id} already exists, skipping")
        return

    # Construct full artwork entry
    artwork_entry = {
        "id": metadata["id"],
        "imageUrl": image_url,
        "title": metadata["title"],
        "artistStatement": metadata.get("artistStatement", ""),
        "redditPostUrl": metadata["redditPostUrl"],
        "createdAt": metadata["createdAt"],
        "videoUrl": metadata.get("videoUrl", None),
    }

    # Append new artwork
    gallery_metadata["artworks"].append(artwork_entry)
    gallery_metadata["lastUpdated"] = datetime.now(timezone.utc).isoformat()

    # Save updated metadata
    with open(GALLERY_METADATA_PATH, "w") as f:
        json.dump(gallery_metadata, f, indent=2)

    activity.logger.info(f"✓ Appended {artwork_id} to gallery metadata")


@activity.defn
async def rebuild_static_site() -> None:
    """
    Rebuild the SvelteKit static site using npm.

    Runs `npm run build` in the gallery directory.
    """
    activity.logger.info("Rebuilding static site...")

    try:
        result = subprocess.run(
            ["npm", "run", "build"],
            cwd=str(GALLERY_DIR),
            capture_output=True,
            text=True,
            check=True,
            timeout=60,  # 1 minute timeout
        )

        activity.logger.info("✓ Build completed successfully")
        activity.logger.debug(f"Build output: {result.stdout}")

    except subprocess.CalledProcessError as e:
        activity.logger.error(f"✗ Build failed with exit code {e.returncode}")
        activity.logger.error(f"stdout: {e.stdout}")
        activity.logger.error(f"stderr: {e.stderr}")
        raise
    except subprocess.TimeoutExpired:
        activity.logger.error("✗ Build timed out after 1 minute")
        raise


@activity.defn
async def deploy_to_cloudflare() -> str:
    """
    Deploy the built site to Cloudflare Workers using wrangler.

    Runs `wrangler deploy` in the gallery directory.

    Returns:
        Gallery URL (e.g., https://claudedraws.com)
    """
    activity.logger.info("Deploying to Cloudflare Workers...")

    try:
        result = subprocess.run(
            ["wrangler", "deploy"],
            cwd=str(GALLERY_DIR),
            capture_output=True,
            text=True,
            check=True,
            timeout=60,  # 1 minute timeout
        )

        activity.logger.info("✓ Deployment completed successfully")
        activity.logger.debug(f"Deploy output: {result.stdout}")

        # Return the gallery URL (customize based on your domain)
        gallery_url = "https://claudedraws.com"
        return gallery_url

    except subprocess.CalledProcessError as e:
        activity.logger.error(f"✗ Deployment failed with exit code {e.returncode}")
        activity.logger.error(f"stdout: {e.stdout}")
        activity.logger.error(f"stderr: {e.stderr}")
        raise
    except subprocess.TimeoutExpired:
        activity.logger.error("✗ Deployment timed out after 1 minute")
        raise
