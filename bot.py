import openai
from telegram.ext import ApplicationBuilder, MessageHandler, filters

openai.api_key = "DEIN_OPENAI_KEY"

async def reply(update, context):
    user_text = update.message.text

    response = openai.ChatCompletion.create(
        model="gpt-4o-mini",
        messages=[{"role":"user","content":user_text}]
    )

    answer = response.choices[0].message.content
    await update.message.reply_text(answer)

app = ApplicationBuilder().token("DEIN_TELEGRAM_TOKEN").build()

app.add_handler(MessageHandler(filters.TEXT, reply))

app.run_polling()