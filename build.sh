#!/usr/bin/env bash
# exit on error
set -o errexit

echo "--- STARTING BUILD ---"

# 1. Install dependencies
echo "Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# 2. Install Playwright browsers
echo "Installing Playwright Chromium..."
# We omit --with-deps because it requires sudo, which isn't available on Render's native env.
# Render's Python environment usually comes pre-packaged with the necessary system libs.
export PLAYWRIGHT_BROWSERS_PATH=/opt/render/project/playwright
python -m playwright install chromium

echo "--- BUILD COMPLETE ---"
