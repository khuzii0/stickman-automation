"""Phase 1: generate the script/storyboard through a resilient LLM provider router."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import requests

from ..config import settings
from ..models import Scene, StoryBoard, slugify

log = logging.getLogger("stickman_studio.phase1")

_SYSTEM_INSTRUCTION = """
You are the Storyboard Architect for Stickman Studio, specializing in engaging educational videos.
Use a strong hook in scene 1, short conversational narration, and visual comedy where appropriate.
Style: minimalist black line art, simple round head, thin limbs, no color, no shading.
Return only valid JSON matching the requested structure. Do not use Markdown fences.
""".strip()


def _storyboard_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "script": {"type": "string"},
            "character_reference_prompt": {"type": "string"},
            "scenes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "scene_prompt": {"type": "string"},
                        "narration": {"type": "string"},
                    },
                    "required": ["title", "scene_prompt", "narration"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["script", "character_reference_prompt", "scenes"],
        "additionalProperties": False,
    }


def _build_prompt(topic: str, scene_count: int) -> str:
    return f"""TOPIC: {topic!r}

Produce a storyboard with:
- script: a concise master narration assembled from the scene narrations; avoid duplicating long text
- character_reference_prompt: a detailed description of the recurring stickman
- scenes: exactly {scene_count} objects

Each scene must contain title, scene_prompt, and narration. Keep each narration around 60-90 words.
scene_prompt should describe only action and environment; do not repeat character identity rules.
The first scene must hook the viewer immediately."""


def _strip_json_fence(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        lines = raw.splitlines()[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        return "\n".join(lines).strip()
    return raw


def _gemini(prompt: str) -> str:
    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is not configured")

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=settings.gemini_api_key)
    response = client.models.generate_content(
        model=settings.gemini_model,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=_SYSTEM_INSTRUCTION,
            max_output_tokens=4096,
            response_mime_type="application/json",
            response_schema=_storyboard_schema(),
        ),
    )
    return response.text or ""


def _request_json(url: str, api_key: str, payload: dict) -> dict:
    response = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=90,
    )
    if not response.ok:
        preview = response.text[:500].replace("\n", " ")
        raise RuntimeError(f"HTTP {response.status_code}: {preview}")
    try:
        return response.json()
    except requests.exceptions.JSONDecodeError as exc:
        preview = response.text[:500].replace("\n", " ")
        raise RuntimeError(
            f"Provider returned a non-JSON HTTP response (status {response.status_code}): {preview!r}"
        ) from exc


def _message_content(payload: dict) -> str:
    try:
        content = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        preview = json.dumps(payload, ensure_ascii=False)[:700]
        raise RuntimeError(f"Unexpected provider response shape: {preview}") from exc
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("Provider returned empty message content")
    return content


def _groq(prompt: str) -> str:
    if not settings.groq_api_key:
        raise RuntimeError("GROQ_API_KEY is not configured")

    payload = _request_json(
        "https://api.groq.com/openai/v1/chat/completions",
        settings.groq_api_key,
        {
            "model": settings.groq_model,
            "messages": [
                {"role": "system", "content": _SYSTEM_INSTRUCTION},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
            "max_tokens": 4096,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "stickman_storyboard",
                    "strict": True,
                    "schema": _groq_storyboard_schema(),
                },
            },
        },
    )
    return _message_content(payload)


def _openrouter(prompt: str) -> str:
    if not settings.openrouter_api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not configured")

    payload = _request_json(
        "https://openrouter.ai/api/v1/chat/completions",
        settings.openrouter_api_key,
        {
            "model": settings.openrouter_model,
            "messages": [
                {"role": "system", "content": _SYSTEM_INSTRUCTION},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
            "max_tokens": 4096,
            "response_format": {"type": "json_object"},
        },
    )
    return _message_content(payload)


def _validate(raw: str, scene_count: int) -> dict:
    raw = _strip_json_fence(raw)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        preview = raw[:700].replace("\n", " ")
        raise ValueError(f"invalid JSON output: {exc}; preview={preview!r}") from exc

    required = ("script", "character_reference_prompt", "scenes")
    missing = [key for key in required if key not in data]
    if missing:
        raise ValueError(f"missing fields: {', '.join(missing)}")
    if not isinstance(data["scenes"], list) or len(data["scenes"]) != scene_count:
        raise ValueError(f"returned {len(data.get('scenes', []))} scenes; expected {scene_count}")
    for i, scene in enumerate(data["scenes"], 1):
        for key in ("title", "scene_prompt", "narration"):
            if not scene.get(key):
                raise ValueError(f"scene {i} missing {key}")
    return data


def _generate(prompt: str, scene_count: int) -> tuple[dict, str]:
    handlers = {"gemini": _gemini, "groq": _groq, "openrouter": _openrouter}
    errors: list[str] = []

    for provider in settings.llm_providers:
        handler = handlers.get(provider)
        if handler is None:
            log.warning("Unknown LLM provider '%s'; skipping.", provider)
            continue

        key_present = {
            "gemini": bool(settings.gemini_api_key),
            "groq": bool(settings.groq_api_key),
            "openrouter": bool(settings.openrouter_api_key),
        }[provider]
        if not key_present:
            log.info("LLM provider %s is not configured; skipping.", provider)
            continue

        model = {
            "gemini": settings.gemini_model,
            "groq": settings.groq_model,
            "openrouter": settings.openrouter_model,
        }[provider]

        try:
            log.info("Trying LLM provider %s (%s)", provider, model)
            raw = handler(prompt)
            data = _validate(raw, scene_count)
            log.info("LLM provider %s succeeded.", provider)
            return data, provider
        except Exception as exc:
            summary = f"{type(exc).__name__}: {exc}"
            errors.append(f"{provider}: {summary}")
            log.warning("LLM provider %s failed; falling back. %s", provider, summary)

    if not errors:
        raise RuntimeError(
            "No LLM provider is configured. Set at least one of GEMINI_API_KEY, GROQ_API_KEY, "
            "or OPENROUTER_API_KEY in .env."
        )
    raise RuntimeError("All configured LLM providers failed:\n- " + "\n- ".join(errors))


def run(topic: str, project_dir: Path, scene_count: int | None = None) -> StoryBoard:
    scene_count = scene_count or settings.scene_count
    log.info("Phase 1: generating script + %d scenes for '%s'", scene_count, topic)
    data, provider = _generate(_build_prompt(topic, scene_count), scene_count)

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
    log.info("Phase 1 complete via %s: %d scenes -> %s", provider, len(scenes), out)
    return board
