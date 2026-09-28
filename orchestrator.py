"""Main entry point for the zero-cost Stickman Studio pipeline."""

from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path
from typing import Optional

import click

from stickman_studio.config import settings, init_vertex
from stickman_studio.logging_setup import configure_logging
from stickman_studio.models import StoryBoard, slugify

import ai_engine
from tts_engine import TTSEngine
from uploader import YouTubeUploader

log = logging.getLogger("stickman_studio.orchestrator")


def run_pipeline(
    topic: str,
    scenes: Optional[int] = None,
    video_mode: str = "slideshow",
    no_video: bool = False,
    no_audio: bool = False,
    upload: bool = False,
    bucket: Optional[str] = None,
    project_dir: Optional[str] = None,
) -> dict:
    """Run script -> images -> TTS -> slideshow/optional Veo -> assembly."""
    root = Path(project_dir) if project_dir else Path.cwd() / "projects"
    out = root / slugify(topic)
    out.mkdir(parents=True, exist_ok=True)
    start = time.time()

    sb_path = out / "storyboard.json"
    if sb_path.is_file():
        log.info("Phase 1: cached storyboard")
        board = StoryBoard.load(sb_path)
    else:
        log.info("Phase 1: Gemini API")
        board = ai_engine.generate_script(topic, out, scenes)

    all_images_cached = all(s.image_path and Path(s.image_path).is_file() for s in board.scenes)
    if all_images_cached:
        log.info("Phase 2: all images cached")
    else:
        log.info("Phase 2: image provider=%s", settings.image_provider)
        board = ai_engine.generate_images(board, out)

    audio_paths: list[Path] | None = None
    if not no_audio:
        audio_dir = out / "audio"
        cached = [audio_dir / f"scene_{i:02d}.mp3" for i in range(len(board.scenes))]
        if all(p.is_file() for p in cached):
            audio_paths = cached
            log.info("Phase 3: all TTS audio cached")
        else:
            log.info("Phase 3: edge-tts")
            audio_paths = TTSEngine().generate_per_scene_audio(board.scenes, audio_dir)

    if video_mode.lower() == "slideshow" and audio_paths:
        if not all(s.video_path and Path(s.video_path).is_file() for s in board.scenes):
            log.info("Phase 4: local FFmpeg slideshow")
            board = ai_engine.generate_slideshow(board, out, audio_paths)
        else:
            log.info("Phase 4: slideshow clips cached")
    elif video_mode.lower() == "animation" and not no_video:
        init_vertex()
        log.info("Phase 4: optional Vertex/Veo animation")
        board = ai_engine.generate_videos(board, out)
    elif video_mode.lower() not in {"slideshow", "animation"}:
        raise ValueError("video_mode must be 'slideshow' or 'animation'")

    final_path = out / "final.mp4"
    manifest_path = out / "manifest.json"
    if final_path.is_file() and manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        summary = {
            "project_dir": str(out),
            "manifest": str(manifest_path),
            "final_video": str(final_path),
            "scene_count": len(board.scenes),
            "images": sum(bool(s.image_path) for s in board.scenes),
            "videos": sum(bool(s.video_path) for s in board.scenes),
            "audio_tracks": len(audio_paths) if audio_paths else 0,
            "topic": manifest.get("topic", topic),
            "_cached": True,
        }
    else:
        log.info("Phase 5: assembly")
        summary = ai_engine.assemble_project(board, out, audio_paths)
        summary["topic"] = topic

    summary["elapsed_seconds"] = time.time() - start

    # GCS upload is deliberately not part of zero-cost mode. Keep the argument
    # for backward compatibility but fail clearly instead of silently charging.
    if upload:
        raise RuntimeError("GCS upload is disabled in zero-cost mode; remove --upload.")

    return summary


@click.command(context_settings={"max_content_width": 100})
@click.argument("topic", required=True)
@click.option("--scenes", "-s", default=None, type=int)
@click.option("--video-mode", "-vm", default="slideshow", type=click.Choice(["animation", "slideshow"], case_sensitive=False))
@click.option("--no-video", is_flag=True, default=False)
@click.option("--no-audio", is_flag=True, default=False)
@click.option("--upload", "-u", is_flag=True, default=False, help="Disabled in zero-cost mode (GCS).")
@click.option("--bucket", "-b", default=None, help="Legacy option; unused in zero-cost mode.")
@click.option("--project-dir", "-d", default=None)
@click.option("--youtube", "-yt", is_flag=True, default=False)
@click.option("--privacy", default="private", type=click.Choice(["private", "unlisted", "public"], case_sensitive=False))
@click.option("--verbose", "-v", is_flag=True, default=False)
def main(topic, scenes, video_mode, no_video, no_audio, upload, bucket, project_dir, youtube, privacy, verbose):
    configure_logging("DEBUG" if verbose else settings.log_level)
    try:
        summary = run_pipeline(topic, scenes, video_mode, no_video, no_audio, upload, bucket, project_dir)
        if youtube:
            _upload_to_youtube(summary, privacy)
        log.info("Done in %.1fs: %s", summary["elapsed_seconds"], summary["final_video"])
    except Exception as exc:
        log.exception("Pipeline failed: %s", exc)
        sys.exit(1)


def _upload_to_youtube(summary: dict, privacy: str = "private") -> None:
    video = summary.get("final_video")
    if not video or not Path(video).is_file():
        log.warning("No final video found; skipping YouTube upload.")
        return
    project_dir = Path(summary.get("project_dir", ""))
    title = summary.get("topic", "Stickman Studio Video")
    description = f"Generated by Stickman Studio — {title}"
    manifest_path = project_dir / "manifest.json"
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            description = f"{title}\n\nGenerated by Stickman Studio\n\n{manifest.get('script', '')[:2000]}"
        except Exception:
            pass
    uploader = YouTubeUploader()
    url = uploader.authenticate_and_upload(
        video_path=video,
        title=title,
        description=description,
        tags=["stickman", "education", "animation", title.lower()],
        privacy_status=privacy,
        auto_publish=privacy == "public",
    )
    log.info("YouTube upload complete: %s", url)


if __name__ == "__main__":
    main()
