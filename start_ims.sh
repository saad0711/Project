#!/bin/bash
# start_ims.sh - Automated startup for IMS Core

echo "🌿 Starting IMS Core Environment..."

# Check if venv exists, if not create it
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate venv
source venv/bin/activate

# Install/Update dependencies
echo "Ensuring dependencies are up to date..."
pip install -q -r requirements.txt

# Run the app
echo "🚀 Internal server starting at http://127.0.0.1:8000"
uvicorn main:app --reload
