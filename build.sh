#!/usr/bin/env bash
# exit on error
set -o errexit

echo "--- STARTING BUILD ---"

# 1. Install dependencies
echo "Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# 2. Install Playwright "Headless Shell" ONLY
# This is a lighter-weight version of Chromium designed for RAM-constrained environments
echo "Installing Playwright Chromium (Headless Shell)..."
export PLAYWRIGHT_BROWSERS_PATH=/opt/render/project/playwright
python -m playwright install --with-deps chromium

echo "--- BUILD COMPLETE ---"
