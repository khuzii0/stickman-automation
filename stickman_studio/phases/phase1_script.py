"""Phase 1: generate the script and storyboard with the Gemini API."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from ..config import settings
from ..models import Scene, StoryBoard, slugify
from ..retry import with_retry

log = logging.getLogger("stickman_studio.phase1")

_SYSTEM_INSTRUCTION = """
You are the Storyboard Architect for Stickman Studio, specializing in engaging educational videos.
Use a strong hook in scene 1, short conversational narration, and visual comedy where appropriate.
Style: minimalist black line art, simple round head, thin limbs, no color, no shading.
Return only JSON matching the requested structure.
"""


def _build_prompt(topic: str, scene_count: int) -> str:
    return f"""TOPIC: {topic!r}

Produce JSON with:
- script: approximately 500 words of engaging narration
- character_reference_prompt: a detailed description of the recurring stickman
- scenes: exactly {scene_count} objects

Each scene object must contain title, scene_prompt, and narration.
scene_prompt should describe only action and environment; do not repeat character identity rules.
The first scene must hook the viewer immediately."""


@with_retry
def _generate(prompt: str):
    if not settings.gemini_api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is required for zero-cost mode. Create a key in Google AI Studio and set it in .env."
        )

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=settings.gemini_api_key)
    return client.models.generate_content(
        model=settings.gemini_model,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=_SYSTEM_INSTRUCTION,
            temperature=0.3,
            max_output_tokens=4096,
            response_mime_type="application/json",
            response_schema={
                "type": "OBJECT",
                "properties": {
                    "script": {"type": "STRING"},
                    "character_reference_prompt": {"type": "STRING"},
                    "scenes": {
                        "type": "ARRAY",
                        "items": {
                            "type": "OBJECT",
                            "properties": {
                                "title": {"type": "STRING"},
                                "scene_prompt": {"type": "STRING"},
                                "narration": {"type": "STRING"},
                            },
                            "required": ["title", "scene_prompt", "narration"],
                        },
                    },
                },
                "required": ["script", "character_reference_prompt", "scenes"],
            },
        ),
    )


def run(topic: str, project_dir: Path, scene_count: int | None = None) -> StoryBoard:
    scene_count = scene_count or settings.scene_count
    log.info("Phase 1 (Gemini API): generating script + %d scenes for '%s'", scene_count, topic)
    response = _generate(_build_prompt(topic, scene_count))
    raw = response.text or ""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Gemini returned invalid JSON: {exc}\n--- raw ---\n{raw[:2000]}") from exc

    if len(data.get("scenes", [])) != scene_count:
        raise RuntimeError(f"Gemini returned {len(data.get('scenes', []))} scenes; expected {scene_count}.")

    scenes = [
        Scene(
            index=i,
            title=item.get("title", f"Scene {i + 1}"),
            scene_prompt=item["scene_prompt"],
            narration=item.get("narration", ""),
        )
        for i, item in enumerate(data["scenes"])
    ]

    board = StoryBoard(
        topic=topic,
        slug=slugify(topic),
        script=data["script"],
        character_reference_prompt=data["character_reference_prompt"],
        scenes=scenes,
    )
    out = board.save(project_dir / "storyboard.json")
    (project_dir / "script.txt").write_text(board.script, encoding="utf-8")
    log.info("Phase 1 complete: %d scenes -> %s", len(scenes), out)
    return board
