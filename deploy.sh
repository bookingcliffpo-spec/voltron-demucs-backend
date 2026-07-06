#!/usr/bin/env bash
# Voltron Demucs Backend — one-shot deploy.
# Run this in THIS folder, on your own machine, where your GitHub + Render logins live.
# It cannot run on Anthropic's side — it needs your accounts.
#
#   chmod +x deploy.sh && ./deploy.sh
#
set -euo pipefail

REPO_NAME="voltron-demucs-backend"
echo "==> Voltron Demucs deploy"

# 1. Requirements
command -v git >/dev/null || { echo "!! git not installed"; exit 1; }
command -v gh  >/dev/null || { echo "!! GitHub CLI (gh) not installed — https://cli.github.com  then: gh auth login"; exit 1; }

# 2. Git init + commit
if [ ! -d .git ]; then
  git init -q
  git branch -M main
fi
git add .
git commit -q -m "Voltron Demucs backend + Base44 integration" || echo "   (nothing new to commit)"

# 3. Create the GitHub repo (idempotent) and push
if gh repo view "$REPO_NAME" >/dev/null 2>&1; then
  echo "==> GitHub repo already exists, pushing..."
  git remote get-url origin >/dev/null 2>&1 || git remote add origin "$(gh repo view "$REPO_NAME" --json url -q .url).git"
  git push -u origin main
else
  echo "==> Creating GitHub repo and pushing..."
  gh repo create "$REPO_NAME" --private --source=. --remote=origin --push
fi

REPO_URL="$(gh repo view "$REPO_NAME" --json url -q .url)"
echo ""
echo "==> Code is on GitHub: $REPO_URL"
echo ""
echo "==> Final 2 steps (Render needs its dashboard — no reliable headless deploy):"
echo "    1) Open:  https://dashboard.render.com/blueprints"
echo "       -> New Blueprint -> pick '$REPO_NAME' -> it reads render.yaml."
echo "       -> Choose the STANDARD plan (Free tier gets OOM-killed by Demucs)."
echo "    2) When it's live, copy the URL and in your Base44 app add the secret:"
echo "          DEMUCS_BACKEND_URL = https://<your-service>.onrender.com"
echo ""
echo "    Then verify:  curl https://<your-service>.onrender.com/health"
echo "    And run:      python test_demucs_backend.py https://<your-service>.onrender.com"
echo ""
echo "==> After the secret is saved, the 'Run Demucs Separation' button runs real Demucs. Done."
