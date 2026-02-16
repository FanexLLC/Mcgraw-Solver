#!/bin/bash
# Startup script for Railway cron service
# This ensures dependencies are installed before running cron.py

set -e  # Exit on error

echo "Installing dependencies..."
pip install -r requirements.txt

echo "Starting cron scheduler..."
python cron.py
