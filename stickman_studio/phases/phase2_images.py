"""Phase 2: generate scene images without requiring Vertex AI."""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from urllib.parse import quote

import requests

from ..config import settings
from ..models import StoryBoard

log = logging.getLogger("stickman_studio.phase2")


def _build_prompt(board: StoryBoard, scene_prompt: str) -> str:
    return (
        f"{board.character_reference_prompt}. ACTION: {scene_prompt}. "
        "Minimalist black line art stickman, simple round head, thin limbs, "
        "plain white background, clean vector-like 2D drawing, black ink only, "
        "high contrast, lots of negative space, no text, no watermark."
    )


def _pollinations_image(prompt: str, output_path: Path) -> None:
    """Best-effort image generation through the Pollinations endpoint."""
    encoded = quote(prompt, safe="")
    url = f"https://image.pollinations.ai/prompt/{encoded}"
    params = {
        "model": settings.pollinations_model,
        "width": settings.image_width,
        "height": settings.image_height,
        "nologo": "true",
        "enhance": "false",
    }
    if settings.pollinations_api_key:
        params["key"] = settings.pollinations_api_key

    output_path.parent.mkdir(parents=True, exist_ok=True)
    last_error: Exception | None = None
    for attempt in range(1, settings.retry_max_attempts + 1):
        try:
            response = requests.get(url, params=params, timeout=180)
            response.raise_for_status()
            content_type = response.headers.get("content-type", "")
            if not response.content or "image" not in content_type.lower():
                raise RuntimeError(f"Image endpoint returned {content_type or 'unknown content type'}")
            output_path.write_bytes(response.content)
            return
        except Exception as exc:
            last_error = exc
            log.warning("Image generation attempt %d/%d failed: %s", attempt, settings.retry_max_attempts, exc)
            if attempt < settings.retry_max_attempts:
                time.sleep(settings.retry_base_delay * attempt)
    raise RuntimeError(f"Image generation failed after retries: {last_error}") from last_error


def _placeholder_image(output_path: Path) -> None:
    """Local fallback that keeps the pipeline operational if an image API is unavailable."""
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (settings.image_width, settings.image_height), "white")
    draw = ImageDraw.Draw(image)
    cx, cy = settings.image_width // 2, settings.image_height // 2
    head = max(35, settings.image_height // 12)
    draw.ellipse((cx - head, cy - 180 - head, cx + head, cy - 180 + head), outline="black", width=5)
    draw.line((cx, cy - 180 + head, cx, cy + 120), fill="black", width=5)
    draw.line((cx, cy - 80, cx - 150, cy + 20), fill="black", width=5)
    draw.line((cx, cy - 80, cx + 150, cy + 20), fill="black", width=5)
    draw.line((cx, cy + 120, cx - 120, cy + 260), fill="black", width=5)
    draw.line((cx, cy + 120, cx + 120, cy + 260), fill="black", width=5)
    image.save(output_path, format="PNG")


def run(board: StoryBoard, project_dir: Path) -> StoryBoard:
    if settings.image_provider not in {"pollinations", "placeholder"}:
        raise RuntimeError(f"Unsupported IMAGE_PROVIDER={settings.image_provider!r}")

    images_dir = project_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    for scene in board.scenes:
        img_path = images_dir / f"scene_{scene.index:02d}.png"
        if img_path.is_file():
            scene.image_path = str(img_path)
            continue

        prompt = _build_prompt(board, scene.scene_prompt)
        log.info("Phase 2: image %d/%d — %s", scene.index + 1, len(board.scenes), scene.title)
        try:
            if settings.image_provider == "placeholder":
                _placeholder_image(img_path)
            else:
                _pollinations_image(prompt, img_path)
        except Exception:
            if settings.image_provider == "pollinations" and os.getenv("IMAGE_FALLBACK_PLACEHOLDER", "1") == "1":
                log.warning("Remote image generation failed; using local placeholder for scene %d", scene.index)
                _placeholder_image(img_path)
            else:
                raise
        scene.image_path = str(img_path)

    board.save(project_dir / "storyboard.json")
    log.info("Phase 2 complete: %d scene images generated", len(board.scenes))
    return board
