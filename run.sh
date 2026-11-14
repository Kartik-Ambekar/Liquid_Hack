#!/bin/bash
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

# Activate virtual environment if present
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# Ensure test samples exist
python samples/generate_samples.py
python samples/generate_wav.py

echo "Starting Sister Offline Health Assistant on http://127.0.0.1:8080 ..."
python start.py
