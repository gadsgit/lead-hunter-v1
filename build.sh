#!/usr/bin/env bash
# exit on error
set -o errexit

# Install python dependencies from the correct file
pip install -r requirements-render.txt

# This ensures the browser is downloaded into the PERSISTENT directory 
# you defined in the Render Dashboard variables.
# We export it here to be absolutely sure during the build phase.
export PLAYWRIGHT_BROWSERS_PATH=/opt/render/project/playwright
python -m playwright install --with-deps chromium
