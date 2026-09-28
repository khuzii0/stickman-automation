from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

from ..models import StoryBoard

log = logging.getLogger("stickman_studio.phase3_slideshow")
_FFMPEG: str | None = None


def _ffmpeg() -> str:
    global _FFMPEG
    if _FFMPEG is None:
        _FFMPEG = shutil.which("ffmpeg")
    if not _FFMPEG:
        raise RuntimeError("FFmpeg was not found on PATH. Install FFmpeg and restart the terminal.")
    return _FFMPEG


def _probe_duration(audio_path: Path) -> float:
    ffmpeg = _ffmpeg()
    ffprobe = shutil.which("ffprobe") or str(Path(ffmpeg).parent / "ffprobe.exe")
    cmd = [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(audio_path)]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, check=False).stdout.strip()
        return float(out) if out else 0.0
    except (ValueError, TypeError, OSError):
        return 0.0


def _ken_burns_clip(image_path: Path, duration: float, output_path: Path) -> Path:
    ffmpeg = _ffmpeg()
    fps = 24
    nframes = max(1, int(duration * fps))
    zoom_inc = 0.1 / nframes
    output_path.parent.mkdir(parents=True, exist_ok=True)
    expr = f"z='min(if(eq(on,1),1,zoom+{zoom_inc}),1.1)':d={nframes}:s=1280x720:fps={fps}"
    cmd = [
        ffmpeg, "-y", "-loop", "1", "-i", str(image_path),
        "-vf", f"scale=1280:720,setsar=1,zoompan={expr}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "27",
        "-t", str(duration), "-pix_fmt", "yuv420p", str(output_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"Ken Burns clip failed: {proc.stderr[-1000:]}")
    return output_path


def run(board: StoryBoard, project_dir: Path, audio_paths: list[Path]) -> StoryBoard:
    videos_dir = project_dir / "videos"
    videos_dir.mkdir(parents=True, exist_ok=True)
    for i, scene in enumerate(board.scenes):
        if not scene.image_path or not Path(scene.image_path).is_file():
            raise RuntimeError(f"Scene {scene.index} has no usable image: {scene.image_path}")
        audio = audio_paths[i] if i < len(audio_paths) else None
        duration = _probe_duration(audio) if audio else 5.0
        duration = duration if duration > 0 else 5.0
        out_path = videos_dir / f"scene_{scene.index:02d}.mp4"
        if not out_path.is_file():
            log.info("Slideshow scene %d/%d — %.1fs", scene.index + 1, len(board.scenes), duration)
            _ken_burns_clip(Path(scene.image_path), duration, out_path)
        scene.video_path = str(out_path)
    board.save(project_dir / "storyboard.json")
    return board
