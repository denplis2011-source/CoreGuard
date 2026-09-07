import os
import re
import logging
from collections import defaultdict
from telegram import Update, ChatPermissions
from telegram.ext import (
    Application, MessageHandler, CommandHandler,
    ContextTypes, filters
)

# ================== CONFIGURATION ==================
TOKEN = "8885507527:AAGMTT4NT_OGXgbwr5CATf45amLKa5wwUYM"                    # ← Remplace par ton vrai token
OPENAI_API_KEY = ""                        # laisse vide pour l’instant
MAX_WARNINGS = 3
MUTE_DURATION = 3600
BAN_AFTER_MUTES = 2

# Mots interdits (FR + EN + RU)
BAD_WORDS = [
    # Français
    "putain", "merde", "connard", "salope", "enculé", "fdp", "ntm", "pd",
    "bite", "couille", "branler", "niquer", "suce", "pute", "bordel", "encule",
    "salopard", "trou du cul", "ta race", "fils de pute",

    # Anglais
    "fuck", "shit", "bitch", "asshole", "cunt", "nigger", "nigga",
    "faggot", "retard", "whore", "slut", "motherfucker", "bastard",

    # Russe (cyrillique)
    "блядь", "блять", "сука", "хуй", "пизда", "ебать", "ебал", "мудак",
    "пидор", "пидр", "долбоёб", "ёб", "нахуй", "пиздец", "ебаный",
    "хуйло", "гандон", "говно", "заебал", "заебись", "ебанутый",
    "хуесос", "пиздос", "блядина", "сучка", "мразь", "тварь",

    # Translittérations russes
    "blyat", "blyad", "suka", "hui", "pizda", "ebat", "ebal", "mudak",
    "pidor", "pidr", "dolboeb", "nahui", "nahuy", "pizdec", "ebanuy",
    "huilo", "gandon", "govno", "zaebal", "ebanutiy", "huesos",
    "blyadina", "suchka", "mraz", "tvar"
]

# ================== CODE ==================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

warnings = defaultdict(int)
mutes = defaultdict(int)

def normalize(text: str) -> str:
    text = text.lower()
    replacements = {
        '0': 'o', '1': 'i', '3': 'e', '4': 'a', '5': 's',
        '7': 't', '@': 'a', '$': 's', '!': 'i'
    }
    for k, v in replacements.items():
        text = text.replace(k, v)
    text = re.sub(r'[^\w\sа-яёàâäéèêëîïôöùûüç]', ' ', text, flags=re.UNICODE)
    return text

def contains_bad_word(text: str) -> bool:
    normalized = normalize(text)
    for word in BAD_WORDS:
        if re.search(rf'\b{re.escape(word)}\b', normalized):
            return True
    return False

async def is_inappropriate_openai(text: str) -> bool:
    if not OPENAI_API_KEY:
        return False
    try:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY)
        response = client.moderations.create(input=text)
        return response.results[0].flagged
    except Exception as e:
        logger.error(f"Erreur OpenAI: {e}")
        return False

async def moderate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    if not message or not message.text:
        return

    user = message.from_user
    chat = message.chat

    # Ignore les admins
    try:
        member = await chat.get_member(user.id)
        if member.status in ("administrator", "creator"):
            return
    except:
        pass

    text = message.text
    is_bad = contains_bad_word(text) or await is_inappropriate_openai(text)

    if not is_bad:
        return

    try:
        await message.delete()
    except Exception as e:
        logger.warning(f"Impossible de supprimer: {e}")
        return

    user_id = user.id
    warnings[user_id] += 1
    warn_count = warnings[user_id]
    mention = user.mention_html()

    if warn_count < MAX_WARNINGS:
        await context.bot.send_message(
            chat_id=chat.id,
            text=f"⚠️ {mention}, message inapproprié supprimé.\nAvertissement {warn_count}/{MAX_WARNINGS}",
            parse_mode="HTML"
        )
    else:
        try:
            await context.bot.restrict_chat_member(
                chat_id=chat.id,
                user_id=user_id,
                permissions=ChatPermissions(can_send_messages=False),
                until_date=message.date.timestamp() + MUTE_DURATION
            )
            mutes[user_id] += 1
            warnings[user_id] = 0

            if mutes[user_id] >= BAN_AFTER_MUTES:
                await context.bot.ban_chat_member(chat.id, user_id)
                await context.bot.send_message(chat.id, f"🚫 {mention} a été banni après plusieurs infractions.")
            else:
                await context.bot.send_message(
                    chat.id,
                    f"🔇 {mention} a été mis en sourdine pour 1 heure (mute {mutes[user_id]}/{BAN_AFTER_MUTES})"
                )
        except Exception as e:
            logger.error(f"Erreur restriction: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🛡️ CoreGuard est actif et protège le groupe.")

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, moderate))
    print("CoreGuard est démarré...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
