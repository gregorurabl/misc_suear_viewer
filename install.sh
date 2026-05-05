#!/usr/bin/env bash
set -e
echo "Installing Suear Viewer dependencies..."
pip install --break-system-packages -r requirements.txt
echo "Done. Run 'python3 app.py' to start."
