#!/bin/bash

cd /root/neutron-botnet
source venv/bin/activate

echo "🔥 Starting NEUTRON Services..."

# Start API server
python3 api_server.py &
API_PID=$!

# Start Telegram bot
python3 telegram_bot.py &
BOT_PID=$!

echo "✅ API Server running on port 8000 (PID: $API_PID)"
echo "✅ Telegram Bot running (PID: $BOT_PID)"
echo ""
echo "Press Ctrl+C to stop all services"

# Save PIDs
echo $API_PID > /tmp/neutron_api.pid
echo $BOT_PID > /tmp/neutron_bot.pid

wait
