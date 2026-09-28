# Zero-Cost Windows Setup

This branch provides a default pipeline that does **not** require Google Cloud billing, Vertex AI, or a GCS staging bucket.

## Pipeline

`Gemini API -> image provider -> edge-tts -> FFmpeg Ken Burns slideshow -> final.mp4`

The optional Veo/Vertex animation path remains available only when GCP credentials and billing are configured.

## 1. Install

From the repository root:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

FFmpeg must be available on PATH:

```powershell
ffmpeg -version
ffprobe -version
```

## 2. Configure Gemini

Copy `.env.example` to `.env` and set:

```env
GEMINI_API_KEY=your_google_ai_studio_key
GEMINI_MODEL=gemini-2.5-flash
IMAGE_PROVIDER=pollinations
IMAGE_FALLBACK_PLACEHOLDER=1
SCENE_COUNT=4
```

The Gemini key is an AI Studio API key, not a Vertex service-account credential.

## 3. First test

Use a short video with four scenes:

```powershell
python orchestrator.py "Why the sky is blue" --scenes 4 --video-mode slideshow
```

The output is under:

```text
projects\why-the-sky-is-blue\final.mp4
```

## 4. Zero-cost requirements

Do **not** set these for the default slideshow pipeline:

```env
GCP_PROJECT_ID=
GOOGLE_APPLICATION_CREDENTIALS=
GCS_STAGING_BUCKET=
```

Do not use:

```powershell
--video-mode animation
--upload
```

`animation` is the optional Vertex/Veo path. `--upload` is deliberately disabled in this branch because it means GCS upload, which is not part of the zero-cost pipeline.

## 5. Image provider caveat

`IMAGE_PROVIDER=pollinations` uses a remote image-generation endpoint. Availability, authentication requirements, rate limits, models, and free access can change. This branch therefore has a local placeholder fallback so the pipeline itself can still be tested without paying for image generation.

For actual YouTube production, verify the current provider's terms and limits before batching large numbers of videos.

## 6. YouTube upload

YouTube upload is independent of Vertex AI. Put a desktop OAuth client file named `client_secrets.json` in the repository root, complete the browser OAuth flow, then use:

```powershell
python orchestrator.py "Why the sky is blue" --scenes 4 --video-mode slideshow --youtube --privacy private
```

Start with `private`. Do not automatically publish a batch until you have reviewed the generated videos.

## 7. Laptop load

The zero-cost path does not run an image or video diffusion model locally. Your laptop only performs TTS orchestration, image downloads, FFmpeg encoding, and final assembly. FFmpeg slideshow encoding uses `veryfast` and CRF 27 by default to reduce CPU load.

## 8. Important limitation

This branch does not reproduce Veo-quality animation or Imagen subject-reference consistency for free. It is intended to validate the YouTube content-production system cheaply before spending money on premium generation.
