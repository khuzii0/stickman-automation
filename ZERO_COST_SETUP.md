# Zero-Cost Windows Setup

This branch provides a default pipeline that does **not** require Google Cloud billing, Vertex AI, or a GCS staging bucket.

## Pipeline

`LLM router (Gemini -> Groq -> OpenRouter) -> image provider -> edge-tts -> FFmpeg Ken Burns slideshow -> final.mp4`

The optional Veo/Vertex animation path remains available only when GCP credentials and billing are configured.

## 1. Install

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

FFmpeg must be on PATH.

## 2. Configure at least one LLM

Copy `.env.example` to `.env`.

Recommended resilient setup:

```env
LLM_PROVIDERS=gemini,groq,openrouter
GEMINI_API_KEY=your_google_ai_studio_key
GEMINI_MODEL=gemini-3.8-flash
GROQ_API_KEY=your_groq_key
GROQ_MODEL=openai/gpt-oss-20b
OPENROUTER_API_KEY=your_openrouter_key
OPENROUTER_MODEL=openrouter/free
```

Providers are tried from left to right. A missing key is skipped. If Gemini returns 503, invalid output, or another error, Phase 1 automatically tries Groq, then OpenRouter.

You do not need all three keys. For the strongest outage protection, configure at least two independent providers.

Never commit or paste your real API keys into GitHub or chat.

## 3. First test

```powershell
python orchestrator.py "Why the sky is blue" --scenes 4 --video-mode slideshow
```

Watch for a log line such as:

```text
Trying LLM provider gemini (...)
LLM provider gemini failed; falling back.
Trying LLM provider groq (...)
LLM provider groq succeeded.
```

The output is under `projects\why-the-sky-is-blue\final.mp4`.

## 4. Provider notes

- Gemini remains first by default, but it is no longer a single point of failure.
- Groq uses its OpenAI-compatible chat-completions API.
- OpenRouter uses `openrouter/free`, which routes to an available zero-cost model.
- Provider/model availability and free limits can change. Keep model IDs in `.env`, not hardcoded in application logic.
- Phase 1 validates the returned JSON and exact scene count before accepting a provider response.

## 5. Zero-cost requirements

Do not configure GCP/Vertex fields for slideshow mode. Do not use `--video-mode animation` or `--upload` for the zero-cost path.

## 6. Image provider caveat

`IMAGE_PROVIDER=pollinations` is a remote best-effort image endpoint. The local placeholder fallback keeps pipeline testing possible if it is unavailable.

## 7. YouTube upload

YouTube upload is independent of Vertex AI. Put `client_secrets.json` in the repository root and start with private uploads.

## 8. Laptop load

The zero-cost path does not run diffusion models locally. The laptop performs orchestration, downloads, TTS, FFmpeg encoding, and assembly.

## 9. Important limitation

This validates the automation architecture cheaply. Free APIs have no production SLA, so a serious production system should retain multiple providers and graceful failure handling.
