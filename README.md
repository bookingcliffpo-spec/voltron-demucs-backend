# Voltron Demucs Backend

Real Python **Demucs** stem-separation server for **Voltron Mastering AI** (Base44 frontend).
FastAPI + PyTorch + FFmpeg, with staged pipeline, structured errors, retry chain, and job polling.

Live Base44 app: https://voltron-master-flow.base44.app

---

## ☕ MORNING CHECKLIST — the only steps left (≈ 5 min)

The whole Base44 side is already done and live. You just need to stand up the server, because
that lives in your Render + GitHub accounts. Do this when you're up:

1. **Get the code on GitHub.** From this folder:
   ```bash
   git init && git add . && git commit -m "Voltron Demucs backend"
   git branch -M main
   git remote add origin https://github.com/<you>/voltron-demucs-backend.git
   git push -u origin main
   ```
   (Or make a new repo on github.com and drag these files into the web uploader.)

2. **Deploy on Render.** Click the button (or Render → New → Blueprint → pick the repo).
   It reads `render.yaml` automatically. **Pick the Standard plan, not Free** — Demucs needs the RAM.

   [![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy)

   First build takes ~10 min (it pre-downloads the model weights).

3. **Paste one secret into Base44.** Copy your Render URL (e.g.
   `https://voltron-demucs-backend.onrender.com`), then in your Base44 app →
   **Settings → Secrets/Environment**:
   ```
   DEMUCS_BACKEND_URL = https://voltron-demucs-backend.onrender.com
   ```
   The moment you save it, the "Run Demucs Separation" button runs real Demucs. Done.

> Until that secret is set, the app won't crash — the button shows a clean message
> ("stem-separation server is not configured yet"), not the old `user-exception`.

---

## Why this exists

Base44 runs your app frontend + Deno backend functions. **Deno cannot load PyTorch or the
Demucs model weights**, so the old `demucsSeparate` function was actually a JavaScript
band-splitter (biquad filters) pretending to be Demucs — and it threw `user-exception`
whenever it ran out of memory on a real song.

This repo is the **real** engine. The Base44 function is now a thin proxy that hands the job
to this server and the browser polls it for progress.

```
Browser (Base44 app)
   │  upload WAV → Base44 storage → file_url
   ▼
Base44 fn: demucsSeparate   ── POST /api/separate_url {file_url} ─►  THIS SERVER (Render)
   │  returns { job_id, backend_url } instantly                         │ fetches file
   ▼                                                                    │ ffmpeg → safe WAV
Browser polls  GET {backend_url}/api/job/{job_id}  ◄────────────────────┤ demucs (htdemucs_ft…)
   │  reads stem URLs when complete                                     │ retry chain
   ▼                                                                    ▼
Stem Mixer loads vocals / drums / bass / other            /api/download/{job}/{stem} + /zip
```

---

## Deploy to Render (≈ 3 clicks + 1 paste)

1. Push this repo to GitHub (see below).
2. In Render: **New → Blueprint**, point it at the repo. It reads `render.yaml` and creates a
   Docker web service. **Do not use the Free tier** — Demucs needs RAM. Use **Standard (2 GB)**
   for `htdemucs`; **Pro (4 GB)** for `htdemucs_ft` on full-length tracks.
3. Wait for the first build (it pre-downloads the model weights, so give it ~10 min).
4. Copy the service URL, e.g. `https://voltron-demucs-backend.onrender.com`.
5. **In Base44**, open your app → **Settings → Secrets/Environment**, add:

   ```
   DEMUCS_BACKEND_URL = https://voltron-demucs-backend.onrender.com
   ```

   That's the only wiring step — the frontend and proxy function are already in your app.

### GitHub

```bash
cd voltron-demucs-backend
git init && git add . && git commit -m "Add production Demucs backend and Base44 integration"
git branch -M main
git remote add origin https://github.com/<you>/voltron-demucs-backend.git
git push -u origin main
```

---

## Verify it's live

```bash
curl https://YOUR-SERVICE.onrender.com/health
# {"ok":true,"service":"voltron-demucs-backend","ffmpeg":true,"python":true,"torch":true,"demucs":true}

curl https://YOUR-SERVICE.onrender.com/api/diagnostics

# Full end-to-end test (health, diagnostics, structured error, real separation, downloads):
pip install requests numpy soundfile
python test_demucs_backend.py https://YOUR-SERVICE.onrender.com
```

Then open the app, upload a short clip, and hit **Run Demucs Separation**. You'll see live
stages (Decoding → Loading model → Separating → Validating) and four real stems load into the mixer.

---

## Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET  | `/health` | ok + ffmpeg/torch/demucs booleans |
| GET  | `/api/diagnostics` | python version, disk, models, CORS, active jobs |
| POST | `/api/separate` | multipart upload (test/direct clients) |
| POST | `/api/separate_url` | `{file_url,filename,model,mode}` — used by Base44 proxy |
| GET  | `/api/job/{job_id}` | live status: `stage`, `progress`, `status`, `stems`, `error` |
| GET  | `/api/download/{job_id}/{stem}` | vocals / drums / bass / other `.wav` |
| GET  | `/api/download/{job_id}/zip` | all stems zipped |

**Modes:** `4stems` (vocals/drums/bass/other) or `2stems` (vocals/no_vocals).
**Models:** `htdemucs_ft` → `htdemucs` → `mdx_extra_q` (automatic retry chain), plus `hdemucs_mmi`.

### Structured errors (never `user-exception`)

```json
{
  "success": false,
  "stage": "running_demucs",
  "message": "Demucs failed during model inference (model: htdemucs_ft).",
  "technical_error": "<real stderr>",
  "stdout": "<real stdout>",
  "retryable": true
}
```

---

## Config (env vars — all optional except the model plan)

| Var | Default | Notes |
|-----|---------|-------|
| `DEMUCS_DEFAULT_MODEL` | `htdemucs` (in render.yaml) | Start with `htdemucs` for speed; `htdemucs_ft` for quality |
| `MAX_FILE_MB` | `100` | Upload cap |
| `MAX_DURATION_SECONDS` | `600` | 10-min track cap |
| `JOB_TTL_SECONDS` | `3600` | Temp files auto-deleted after this |
| `EXTRA_CORS_ORIGINS` | — | Comma-separated extra origins if you add domains |

CORS already allows `https://voltron-master-flow.base44.app` and localhost dev ports.

## Notes / gotchas

- **Cold start:** Render spins the box down when idle; the first request after idle can take
  ~30–60s. The frontend keeps polling through it and shows "Waiting for server…".
- **CPU speed:** A 3–4 min song on a Standard box takes roughly 3–8 min with `htdemucs`.
  `htdemucs_ft` is ~4× slower but cleaner — use Pro plan for it.
- **Persistence:** Stems live for `JOB_TTL_SECONDS`, long enough to download. For permanent
  storage, have the proxy re-upload stems to Base44 (a follow-up option, not required to work).
