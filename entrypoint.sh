#!/bin/bash
echo "Starting Wireproxy..."
./wireproxy -c proxy.conf &
sleep 2 t
python3 -m happybot