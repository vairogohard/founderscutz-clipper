#!/usr/bin/env bash
# Start de installatie. Draai in de VS Code-terminal:  bash setup.sh
set -e
cd "$(dirname "$0")"

if ! command -v git >/dev/null 2>&1 || ! command -v python3 >/dev/null 2>&1; then
  echo "git of python3 ontbreekt. Voer eerst uit:  xcode-select --install"
  echo "Start daarna opnieuw:  bash setup.sh"
  exit 1
fi

if ! command -v gh >/dev/null 2>&1; then
  if command -v brew >/dev/null 2>&1; then
    echo "GitHub CLI installeren..."
    brew install gh
  else
    echo "Homebrew ontbreekt. Installeer het met de opdracht van https://brew.sh"
    echo "Start daarna opnieuw:  bash setup.sh"
    exit 1
  fi
fi

python3 tools/install.py
