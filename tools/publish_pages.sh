#!/usr/bin/env bash
# Zet de clips online via GitHub Pages (branch gh-pages), zonder geschiedenis op te bouwen.
set -euo pipefail
REMOTE="https://x-access-token:${GITHUB_TOKEN}@github.com/${GITHUB_REPOSITORY}.git"
rm -rf _pages _old && mkdir -p _pages/clips
if git ls-remote --exit-code --heads "$REMOTE" gh-pages >/dev/null 2>&1; then
  git clone --quiet --depth 1 --branch gh-pages "$REMOTE" _old
  cp _old/clips/*.mp4 _pages/clips/ 2>/dev/null || true
fi
cp out/clips/*.mp4 _pages/clips/ 2>/dev/null || true
python -m clipper.pages _pages/clips
cd _pages
touch .nojekyll
echo "ok" > index.html
git init --quiet -b gh-pages
git config user.name "clipper-bot"
git config user.email "clipper-bot@users.noreply.github.com"
git add -A
git commit --quiet -m "clips bijgewerkt"
git push --quiet --force "$REMOTE" gh-pages
