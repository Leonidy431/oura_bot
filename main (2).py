import os
import logging
from datetime import datetime, timedelta
import aiohttp
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OURA_PAT = os.getenv("OURA_PAT")
OURA_API = "https://api.ouraring.com/v2/usercollection"

async def get_oura_data(endpoint: str) -> dict:
    headers = {"Authorization": f"Bearer {OURA_PAT}"}
    yesterday = (datetime.utcnow() - timedelta(days=1)).date()
    params = {"start_date": yesterday, "end_date": yesterday}
    
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{OURA_API}/{endpoint}", headers=headers, params=params) as resp:
            return await resp.json() if resp.status == 200 else {"error": "API error"}

async def sleep(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = await get_oura_data("sleep")
    if "data" in data and data["data"]:
        s = data["data"][0]
        text = (f"🛏️ Sleep:\n"
                f"Duration: {s['total_sleep_duration']//3600}h {(s['total_sleep_duration']%3600)//60}m\n"
                f"Deep: {s.get('deep_sleep_duration', 0)//3600}h\n"
                f"REM: {s.get('rem_sleep_duration', 0)//3600}h\n"
                f"Score: {s.get('sleep_score', 'N/A')}")
    else:
        text = "No sleep data available"
    await update.message.reply_text(text)

async def activity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = await get_oura_data("activity")
    if "data" in data and data["data"]:
        a = data["data"][0]
        text = (f"🏃 Activity:\n"
                f"Calories: {a.get('active_calories', 0)}\n"
                f"Steps: {a.get('steps', 0)}\n"
                f"Score: {a.get('activity_score', 'N/A')}")
    else:
        text = "No activity data available"
    await update.message.reply_text(text)

async def readiness(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = await get_oura_data("readiness")
    if "data" in data and data["data"]:
        r = data["data"][0]
        text = (f"💪 Readiness:\n"
                f"Score: {r.get('readiness_score', 'N/A')}\n"
                f"HRV: {r.get('heart_rate_variability_balance', 'N/A')}\n"
                f"Recovery: {r.get('recovery_index', 'N/A')}")
    else:
        text = "No readiness data available"
    await update.message.reply_text(text)

async def main():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("sleep", sleep))
    app.add_handler(CommandHandler("activity", activity))
    app.add_handler(CommandHandler("readiness", readiness))
    await app.run_polling()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
