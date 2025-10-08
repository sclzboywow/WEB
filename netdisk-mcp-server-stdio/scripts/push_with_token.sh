#!/usr/bin/env bash
set -euo pipefail

: "${GITHUB_USERNAME:?GITHUB_USERNAME not set}"
: "${GITHUB_PAT:?GITHUB_PAT not set}"

remote_url="https://${GITHUB_USERNAME}:${GITHUB_PAT}@github.com/sclzboywow/WEB.git"

dir="$(cd "$(dirname "$0")/.." && pwd)"
cd "$dir"

git remote set-url origin "$remote_url"

echo "Pushing to origin main ..."
GIT_ASKPASS= git push origin main

echo "Done."
