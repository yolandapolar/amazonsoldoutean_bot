import json
import pandas as pd
import os
import re
from datetime import datetime
from telegram import Update, InputFile
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

BOT_TOKEN = "7796924221:AAHmGXuwCcvUg0175GyRMQZhTlqmncILbNM"

# Bulgarian welcome and instructions
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Здравей! Моля, изпрати *json* файл – Telegram чат експорт.")

# Extract EAN, Name, Date, Hour
def extract_data(messages):
    rows = []
    last_date = ""
    last_hour = ""

    for msg in messages:
        if not isinstance(msg, dict) or "text" not in msg:
            continue

        text = msg.get("text", "")
        if isinstance(text, list):
            text = "".join([t if isinstance(t, str) else t.get("text", "") for t in text])
        elif not isinstance(text, str):
            continue

        text = text.replace("\n", " ")
        print("------- MESSAGE -------")
        print(text)

        matches = re.findall(r"\b(\d{13})\b\s+(.*?)\s+\((L|M|U)\)", text)
        print("Matches:", matches)

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

# Handle .json file
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

        print(f"FINAL ROW COUNT: {len(df)}")
        print("DATAFRAME PREVIEW:")
        print(df.head())

        if df.empty:
            await update.message.reply_text("❌ Не са открити ЕАН кодове.")
            return

        # Save CSV to disk
        today_str = datetime.today().strftime("%Y-%m-%d")
        export_name = f"Export-chats-Telegram_{today_str}.csv"
        df.to_csv(export_name, index=False, encoding="utf-8-sig")

        # Ensure the file is flushed and re-opened cleanly
        with open(export_name, "rb") as f:
            await update.message.reply_document(InputFile(f, filename=export_name))

    except Exception as e:
        await update.message.reply_text(f"⚠️ Възникна грешка: {str(e)}")

    finally:
        # Don't delete too quickly
        import time
        time.sleep(5)
        if os.path.exists(filename):
            os.remove(filename)
        if export_name and os.path.exists(export_name):
            os.remove(export_name)


# App setup
app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(MessageHandler(filters.TEXT & filters.Regex("(?i)^здравей$"), start))
app.add_handler(MessageHandler(filters.Document.MimeType("application/json"), handle_file))
app.run_polling()
