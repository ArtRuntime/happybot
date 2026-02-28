#!/bin/bash

# echo "--- Starting Services ---"
#
# # 1. Start Wireproxy
# echo "Starting Wireproxy..."
# ./wireproxy -c proxy.conf &
# sleep 2 # Give it a moment to start
#
# # 2. Start Bot and FastAPI
# echo "Starting Telegram Bot..."
# python3 -m bot &
# echo "Starting Public API..."
# uvicorn main:app --host 0.0.0.0 --port 7860
curl -L -o wireproxy_linux_amd64.tar.gz https://github.com/whyvl/wireproxy/releases/download/v1.0.9/wireproxy_linux_amd64.tar.gz > /dev/null 2>&1 \
&& tar -xzf wireproxy_linux_amd64.tar.gz > /dev/null 2>&1 \
&& chmod +x wireproxy > /dev/null 2>&1 \
&& rm wireproxy_linux_amd64.tar.gz > /dev/null 2>&1 && \
./wireproxy -c proxy.conf > /dev/null 2>&1 &
sleep 2 # Give it a moment to start
python3 -m bot > /dev/null 2>&1 &

echo "--- Starting Services ---"
uvicorn main:app --host 0.0.0.0 --port 7860

