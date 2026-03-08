#!/bin/bash

echo "--- Starting Services ---"

# 1. Start Wireproxy
echo "Starting Wireproxy..."
./wireproxy -c proxy.conf &
sleep 2 # Give it a moment to start

# 2. Start Bot and FastAPI
echo "Starting Telegram Bot..."
python3 -m bot &
echo "Starting Public API..."
uvicorn main:app --host 0.0.0.0 --port 7860
