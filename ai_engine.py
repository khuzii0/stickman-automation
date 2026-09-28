"""Optional Vertex helpers plus provider-independent pipeline wrappers."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from stickman_studio.config import settings, init_vertex
from stickman_studio.models import StoryBoard


def generate_script(topic: str, project_dir: str | Path, scene_count: Optional[int] = None) -> StoryBoard:
    from stickman_studio.phases.phase1_script import run
    return run(topic, Path(project_dir), scene_count)


def generate_images(board: StoryBoard, project_dir: str | Path, use_reference: bool = True) -> StoryBoard:
    from stickman_studio.phases.phase2_images import run
    return run(board, Path(project_dir))


def generate_videos(board: StoryBoard, project_dir: str | Path) -> StoryBoard:
    init_vertex()
    from stickman_studio.phases.phase3_video import run
    return run(board, Path(project_dir))


def generate_slideshow(board: StoryBoard, project_dir: str | Path, audio_paths: list[Path]) -> StoryBoard:
    from stickman_studio.phases.phase3_slideshow import run
    return run(board, Path(project_dir), audio_paths)


def add_subtitles(project_dir: str | Path) -> Path | None:
    from stickman_studio.phases.phase4_subtitles import run
    return run(Path(project_dir))


def assemble_project(board: StoryBoard, project_dir: str | Path, audio_paths: Optional[list[Path]] = None) -> dict:
    from stickman_studio.phases.phase4_assembly import run
    return run(board, Path(project_dir), audio_paths)


class AIEngine:
    """Compatibility facade for the optional Vertex/Veo path."""

    def __init__(self) -> None:
        init_vertex()
        self._veo_client = None

    @property
    def veo_client(self):
        if self._veo_client is None:
            from google import genai
            self._veo_client = genai.Client(vertexai=True, project=settings.gcp_project_id, location=settings.gcp_location)
        return self._veo_client
