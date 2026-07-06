#!/bin/bash
echo "Starting Wireproxy..."
./wireproxy -c proxy.conf &
sleep 2
python3 -m bot