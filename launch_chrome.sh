#!/bin/bash
echo "Launching Chrome with debug mode..."
echo "Close ALL Chrome windows first, then run this."
echo ""
echo "Killing any remaining Chrome processes..."
pkill -f "Google Chrome" 2>/dev/null
sleep 2
echo "Starting Chrome..."
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --remote-debugging-port=9222 \
  --user-data-dir="/tmp/chrome-debug" &
echo ""
echo "Chrome launched! Navigate to your SmartBook assignment, then run the solver."
echo "You can verify debug mode at: http://127.0.0.1:9222/json"
