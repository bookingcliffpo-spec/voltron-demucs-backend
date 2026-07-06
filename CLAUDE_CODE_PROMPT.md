# Paste this into Claude Code

Open Claude Code **inside the `voltron-demucs-backend` folder on your own machine**, then paste
the block below. It runs where your GitHub + Render logins already live, so it can actually finish.

> Claude Code can't create a Render account or log into Render for you, but if you've run
> `gh auth login` (GitHub CLI) it can do the whole GitHub side and hand you the Render blueprint
> link + set up verification.

---

```
You are my deploy engineer. The repo in this folder is a FastAPI + PyTorch + Demucs backend
for my Base44 app "Voltron Mastering AI". The frontend and Base44 proxy function are already
wired — the only thing missing is a live server and one Base44 secret.

Do this, checking each step before moving on:

1. Run ./deploy.sh  (it inits git, creates a private GitHub repo via `gh`, and pushes).
   If `gh` isn't authenticated, stop and tell me to run `gh auth login`.

2. Print the GitHub repo URL, then give me the exact Render Blueprint deploy link and remind me
   to pick the STANDARD plan (not Free — Demucs will OOM on Free).

3. Wait for me to paste back the live Render URL. Then:
   - curl the /health endpoint and confirm ffmpeg/torch/demucs are all true.
   - run: python test_demucs_backend.py <render-url>  and report the pass/fail summary.

4. Remind me to add the Base44 secret DEMUCS_BACKEND_URL = <render-url> in my app settings,
   and confirm that's the final wire.

Do not fake any step. If something needs my login or a dashboard click, tell me exactly what to
click and wait. Keep going until /health is green and the test script passes.
```
