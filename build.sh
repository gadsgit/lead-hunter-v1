#!/usr/bin/env bash
# exit on error
set -o errexit

pip install -r requirements-render.txt

# Ensure Playwright is installed and then force the browser binaries
python -m playwright install --with-deps chromium
