import os
import time
import requests
import threading
import asyncio
from dotenv import load_dotenv
from flask import Flask, request
from telegram import Bot, Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# -------------------------
# Configuração inicial
# -------------------------
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
API_FOOTBALL_KEY = os.getenv("API_FOOTBALL_KEY")
TARGET_CHAT_ID = os.getenv("TARGET_CHAT_ID")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", 30))

if not TELEGRAM_BOT_TOKEN:
    print("❌ ERRO: Variável TELEGRAM_BOT_TOKEN não encontrada no Environment!")
else:
    print(f"✅ Token carregado com sucesso: {TELEGRAM_BOT_TOKEN[:10]}...")

bot = Bot(token=TELEGRAM_BOT_TOKEN)
app = Flask(__name__)

sent_signals = set()
lock = threading.Lock()
API_BASE = "https://v3.football.api-sports.io"
HEADERS = {"x-apisports-key": API_FOOTBALL_KEY}

# -------------------------
# Comandos do Telegram
# -------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🚀 BOT_ESCANTEIOS RP™ ativo!\nUse /id para descobrir o chat_id do grupo."
    )

async def get_chat_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"📋 ID do Grupo: {update.effective_chat.id}")

# -------------------------
# Funções de monitoramento
# -------------------------
def fetch_live_fixtures():
    try:
        r = requests.get(f"{API_BASE}/fixtures?live=all", headers=HEADERS, timeout=10)
        return r.json().get("response", [])
    except Exception as e:
        print("Erro buscando jogos ao vivo:", e)
        return []

def build_message(fixture, strategy):
    home = fixture["teams"]["home"]["name"]
    away = fixture["teams"]["away"]["name"]
    score = f'{fixture["goals"]["home"]} x {fixture["goals"]["away"]}'
    minute = fixture["fixture"]["status"]["elapsed"]
    competition = fixture["league"]["name"]
    corners_home = fixture.get("corners", {}).get("home", 0)
    corners_away = fixture.get("corners", {}).get("away", 0)

    msg = (
        f"🚩 Estratégia Detectada: {strategy}\n"
        f"🏟 Jogo: {home} vs {away}\n"
        f"🏆 Competição: {competition}\n"
        f"⏱ Minuto: {minute}'\n"
        f"⚽ Placar: {score}\n"
        f"⛳ Escanteios: {corners_home} - {corners_away}\n"
        f"➡ Entrada sugerida: Escanteios Asiáticos\n"
    )
    return msg

def evaluate_fixture(fixture):
    minute = fixture["fixture"]["status"]["elapsed"]
    corners_home = fixture.get("corners", {}).get("home", 0)
    corners_away = fixture.get("corners", {}).get("away", 0)
    total_corners = corners_home + corners_away

    if 33 <= minute <= 38 and total_corners <= 2:
        return "HT - Alta chance de escanteios"
    elif 83 <= minute <= 87 and total_corners <= 2:
        return "FT - Alta chance de escanteios"
    return None

def monitor_loop():
    while True:
        try:
            fixtures = fetch_live_fixtures()
            for fix in fixtures:
                strategy = evaluate_fixture(fix)
                if not strategy:
                    continue

                fixture_id = fix["fixture"]["id"]
                key = f"{fixture_id}:{strategy}"
                with lock:
                    if key in sent_signals:
                        continue
                    sent_signals.add(key)

                msg = build_message(fix, strategy)
                if TARGET_CHAT_ID:
                    try:
                        bot.send_message(
                            chat_id=int(TARGET_CHAT_ID),
                            text=msg,
                            parse_mode="Markdown"
                        )
                    except Exception as e:
                        print("Erro enviando mensagem:", e)
                else:
                    print(msg)
        except Exception as e:
            print("Erro no loop principal:", e)

        time.sleep(POLL_INTERVAL)

# -------------------------
# Webhook Flask
# -------------------------
@app.route(f"/{TELEGRAM_BOT_TOKEN}", methods=["POST"])
def webhook():
    json_update = request.get_json(force=True)
    update = Update.de_json(json_update, bot)
    # Executa o processamento de forma assíncrona
    application.create_task(application.process_update(update))
    return "OK"

@app.route("/")
def index():
    return "✅ BOT_ESCANTEIOS RP rodando com sucesso!"

# -------------------------
# Setup Telegram
# -------------------------
application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("id", get_chat_id))

# -------------------------
# Main
# -------------------------
if __name__ == "__main__":
    async def setup_webhook():
        await bot.delete_webhook()
        url = f"https://bot-escanteios17.onrender.com/{TELEGRAM_BOT_TOKEN}"
        await bot.set_webhook(url)
        print(f"🌐 Webhook configurado: {url}")

    asyncio.run(setup_webhook())

    threading.Thread(target=monitor_loop, daemon=True).start()

    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)