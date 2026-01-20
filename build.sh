#!/usr/bin/env bash
# exit on error
set -o errexit

pip install -r requirements-render.txt

# Ensure Playwright finds the correct folder on Render
export PLAYWRIGHT_BROWSERS_PATH=/opt/render/project/playwright

# Ensure Playwright is installed and then force the browser binaries
python -m playwright install --with-deps chromium
