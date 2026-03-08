import os
import sys
import logging
from pathlib import Path


def fail(message):
    print(message, file=sys.stderr, flush=True)
    raise SystemExit(1)


def looks_like_placeholder(value):
    normalized = value.strip().upper()
    placeholders = {
        "DEIN_BOT_TOKEN",
        "YOUR_BOT_TOKEN",
        "BOT_TOKEN",
        "DEIN_OPENAI_API_KEY",
        "YOUR_OPENAI_API_KEY",
        "OPENAI_API_KEY",
    }
    return normalized in placeholders


try:
    from dotenv import load_dotenv
    from openai import (
        APIConnectionError,
        APIStatusError,
        AuthenticationError,
        BadRequestError,
        NotFoundError,
        OpenAI,
        PermissionDeniedError,
        RateLimitError,
    )
    from telegram.error import InvalidToken, NetworkError, TelegramError
    from telegram.ext import Application, ApplicationBuilder, CommandHandler, MessageHandler, filters
except ImportError as exc:
    missing_package = exc.name or str(exc)
    fail(
        "Missing dependency while starting the bot.\n"
        f"Import failed: {missing_package}\n"
        "Use the project virtual environment: `source venv/bin/activate && python bot.py`\n"
        "Or install packages with: `pip install -r requirements.txt`"
    )


ENV_PATH = Path(__file__).with_name(".env")
load_dotenv(dotenv_path=ENV_PATH, override=True)
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

missing_env_vars = [
    name
    for name, value in {
        "TELEGRAM_BOT_TOKEN": TELEGRAM_TOKEN,
        "OPENAI_API_KEY": OPENAI_API_KEY,
    }.items()
    if not value
]

if missing_env_vars:
    fail(
        "Missing required environment variables: "
        + ", ".join(missing_env_vars)
        + "\nAdd them to your `.env` file before starting the bot."
    )

if looks_like_placeholder(TELEGRAM_TOKEN):
    fail(
        "TELEGRAM_BOT_TOKEN still contains a placeholder value.\n"
        "Open `.env` and replace it with the real token from @BotFather.\n"
        "If `.env` is already correct, remove stale shell variables with:\n"
        "`unset TELEGRAM_BOT_TOKEN OPENAI_API_KEY`"
    )

if looks_like_placeholder(OPENAI_API_KEY):
    fail(
        "OPENAI_API_KEY still contains a placeholder value.\n"
        "Open `.env` and replace it with your real OpenAI API key."
    )


client = OpenAI(api_key=OPENAI_API_KEY)


async def on_startup(application: Application):
    bot_info = await application.bot.get_me()
    bot_name = bot_info.username or bot_info.first_name or "unknown"
    print(f"Bot is running as @{bot_name}.", flush=True)


async def start(update, context):
    if update.message is None:
        return

    await update.message.reply_text(
        "Bot is online. Send any normal text message and I will forward it to OpenAI."
    )


async def ping(update, context):
    if update.message is None:
        return

    await update.message.reply_text("pong")


async def reply(update, context):
    if update.message is None or not update.message.text:
        return

    user_text = update.message.text
    logging.info("Received message with %s characters", len(user_text))

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": user_text}],
        )
    except AuthenticationError as exc:
        logging.exception("OpenAI authentication failed")
        await update.message.reply_text(
            "OpenAI authentication failed. Replace OPENAI_API_KEY with a real API key from "
            "platform.openai.com/api-keys."
        )
        return
    except RateLimitError as exc:
        logging.exception("OpenAI rate limit or quota issue")
        error_body = getattr(exc, "body", {}) or {}
        error_info = error_body.get("error", {}) if isinstance(error_body, dict) else {}
        error_code = error_info.get("code")

        if error_code == "insufficient_quota":
            await update.message.reply_text(
                "OpenAI API quota is exhausted or not enabled for this project. "
                "Add API billing/credits in the OpenAI Platform and make sure this API key "
                "belongs to that billed project."
            )
        else:
            await update.message.reply_text(
                "OpenAI request was rejected due to rate limiting. Try again later."
            )
        return
    except PermissionDeniedError as exc:
        logging.exception("OpenAI permission denied")
        await update.message.reply_text(
            "OpenAI denied access to this request. Your API key may not have access to the model."
        )
        return
    except NotFoundError as exc:
        logging.exception("OpenAI model or endpoint not found")
        await update.message.reply_text(
            "OpenAI could not find the requested model. The configured model may be unavailable."
        )
        return
    except BadRequestError as exc:
        logging.exception("OpenAI rejected the request as invalid")
        await update.message.reply_text(
            "OpenAI rejected the request as invalid. See the terminal for the exact API error."
        )
        return
    except APIConnectionError as exc:
        logging.exception("OpenAI connection failed")
        await update.message.reply_text(
            "OpenAI connection failed. Check internet access, DNS, proxy settings, or firewall."
        )
        return
    except APIStatusError as exc:
        logging.exception("OpenAI returned an API status error")
        await update.message.reply_text(
            f"OpenAI API error {exc.status_code}. See the terminal for details."
        )
        return
    except Exception as exc:
        logging.exception("Unexpected OpenAI failure")
        await update.message.reply_text(
            "Unexpected OpenAI error. See the terminal output for the exact exception."
        )
        return

    answer = response.choices[0].message.content or "The model returned an empty response."
    await update.message.reply_text(answer)


def main():
    print("Starting bot...", flush=True)

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).post_init(on_startup).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ping", ping))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, reply))

    try:
        app.run_polling()
    except InvalidToken:
        fail("Telegram rejected TELEGRAM_BOT_TOKEN. Check the token value in your `.env` file.")
    except NetworkError as exc:
        fail(
            "Telegram connection failed. Check internet access, DNS, and TELEGRAM_BOT_TOKEN.\n"
            f"Details: {exc}"
        )
    except TelegramError as exc:
        fail(f"Telegram startup failed: {exc}")


if __name__ == "__main__":
    main()
