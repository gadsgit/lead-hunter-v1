#!/usr/bin/env bash
# exit on error
set -o errexit

# 1. Install Python packages
pip install -r requirements.txt

# 2. Tell Playwright to install the browser into our persistent directory
# This ensures it survives the move from "Build" to "Run"
PLAYWRIGHT_BROWSERS_PATH=/opt/render/project/playwright python -m playwright install --with-deps chromium
