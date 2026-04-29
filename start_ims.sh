#!/bin/bash
# start_ims.sh - starts the inventory management system

echo "Starting IMS..."

# make venv if it doesnt exist
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# activate it
source venv/bin/activate

# install stuff
echo "Installing dependencies..."
pip install -q -r requirements.txt

# run the server
echo "Server starting at http://127.0.0.1:8000"
uvicorn main:app --reload
