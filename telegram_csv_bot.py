import os
import json
import pandas as pd
import re
from datetime import datetime
from telegram import Update, InputFile
from telegram.ext import Application, MessageHandler, filters, ContextTypes, CommandHandler
from telegram.request import HTTPXRequest
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
import uvicorn

# --- Config ---
BOT_TOKEN = os.environ.get("BOT_TOKEN")
request_con = HTTPXRequest()
application = Application.builder().token(BOT_TOKEN).request(request_con).build()

# --- FastAPI Setup ---
api = FastAPI()

# --- Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Здравей! Моля, изпрати *json* файл – Telegram чат експорт.")

def extract_data(messages):
    rows = []
    last_date = ""
    last_hour = ""
    skip_until_next_noverstock = False

    for msg in messages:
        if not isinstance(msg, dict) or "text" not in msg:
            continue

        text = msg.get("text", "")
        if isinstance(text, list):
            text = "".join([t if isinstance(t, str) else t.get("text", "") for t in text])
        elif not isinstance(text, str):
            continue

        text = text.replace("\n", " ")

        if "Pulheim Transfer" in text:
            skip_until_next_noverstock = True
            continue

        if "Noverstock" in text:
            skip_until_next_noverstock = False

        if skip_until_next_noverstock:
            continue

        matches = re.findall(r"\b(\d{13})\b\s+(.*?)(?:\s+\((L|M|U|SPF)\))?", text)

        date_full = msg.get("date")
        if date_full:
            dt = datetime.fromisoformat(date_full)
            last_date = dt.strftime("%d %B %Y")
            last_hour = dt.strftime("%H:%M")

        for ean, name, _ in matches:
            if last_date and last_hour:
                rows.append({
                    "Date": last_date,
                    "Hour": last_hour,
                    "EAN": ean,
                    "Name": name.strip(),
                    "Forecast URL": f"https://mytrendylady.com/administration/forecast/show/{ean}"
                })

    df = pd.DataFrame(rows)
    df.drop_duplicates(inplace=True)
    return df

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file = await update.message.document.get_file()
    filename = f"{file.file_id}.json"
    await file.download_to_drive(filename)

    export_name = ""
    try:
        with open(filename, "r", encoding="utf-8") as f:
            data = json.load(f)

        messages = data.get("messages", [])
        df = extract_data(messages)

        if df.empty:
            await update.message.reply_text("❌ Не са открити ЕАН кодове.")
            return

        today_str = datetime.today().strftime("%Y-%m-%d")
        export_name = f"Export-chats-Telegram_{today_str}.csv"
        df.to_csv(export_name, index=False, encoding="utf-8-sig")

        with open(export_name, "rb") as f:
            await update.message.reply_document(InputFile(f, filename=export_name))

    except Exception as e:
        await update.message.reply_text(f"⚠️ Възникна грешка: {str(e)}")
    finally:
        if os.path.exists(filename):
            os.remove(filename)
        if export_name and os.path.exists(export_name):
            os.remove(export_name)

# --- Register Handlers ---
@api.on_event("startup")
async def startup_event():
    await application.initialize()
    await application.start()
    application.updater = None

application.add_handler(CommandHandler("start", start))
application.add_handler(MessageHandler(filters.TEXT & filters.Regex("(?i)^здравей$"), start))
application.add_handler(MessageHandler(filters.Document.MimeType("application/json"), handle_file))

# --- FastAPI Webhook Endpoint ---
@api.post("/webhook/{token}")
async def telegram_webhook(request: Request, token: str):
    if token != BOT_TOKEN:
        return PlainTextResponse("Invalid token", status_code=403)

    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.process_update(update)
    return PlainTextResponse("ok")

# --- Health Check ---
@api.get("/")
async def root():
    return PlainTextResponse("Bot is running!")

# --- Main Entry Point ---
if __name__ == "__main__":
    uvicorn.run("telegram_csv_bot:api", host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
