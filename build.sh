#!/usr/bin/env bash
# exit on error
set -o errexit

# Install all combined requirements
pip install -r requirements.txt

# Download the browser ONLY on Render's server
# We use the path variable you set in the Render Dashboard
python -m playwright install --with-deps chromium
