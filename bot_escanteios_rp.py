# bot_escanteios_rp.py
# -------------------------
# Versão webhook, envio de sinais ao vivo
# -------------------------

import os
import time
import requests
import threading
from dotenv import load_dotenv
from flask import Flask, request
from telegram import Bot, Update
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# -------------------------
# Carrega variáveis do .env
# -------------------------
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
API_FOOTBALL_KEY = os.getenv("API_FOOTBALL_KEY")
TARGET_CHAT_ID = os.getenv("TARGET_CHAT_ID")  # opcional, pode deixar vazio e pegar com /id
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", 30))  # segundos

if not TELEGRAM_BOT_TOKEN or not API_FOOTBALL_KEY:
    raise RuntimeError("VERIFIQUE: TELEGRAM_BOT_TOKEN e API_FOOTBALL_KEY precisam estar no .env")

bot = Bot(token=TELEGRAM_BOT_TOKEN)
app = Flask(_name_)

API_BASE = "https://v3.football.api-sports.io"
HEADERS = {"x-apisports-key": API_FOOTBALL_KEY}
sent_signals = set()
lock = threading.Lock()

# -------------------------
# Comandos Telegram
# -------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "BOT_ESCANTEIOS RP™ está ativo! Use /id para descobrir o chat_id do grupo."
    )

async def get_chat_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"📋 ID do Grupo: {update.effective_chat.id}")

# -------------------------
# Funções de monitoramento
# -------------------------
def fetch_live_fixtures():
    url = f"{API_BASE}/fixtures?live=all"
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        data = r.json()
        return data.get("response", [])
    except Exception as e:
        print("Erro fetch_live_fixtures:", e)
        return []

def fetch_fixture_statistics(fixture_id):
    url = f"{API_BASE}/fixtures/statistics?fixture={fixture_id}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        data = r.json()
        return data.get("response", [])
    except Exception as e:
        print("Erro fetch_fixture_statistics:", e)
        return []

def build_message(fixture, strategy):
    home = fixture["teams"]["home"]["name"]
    away = fixture["teams"]["away"]["name"]
    score = f'{fixture["goals"]["home"]} x {fixture["goals"]["away"]}'
    minute = fixture["fixture"]["status"]["elapsed"]
    competition = fixture["league"]["name"]

    msg = f"🚩 Alerta Estratégia: {strategy}\n"
    msg += f"🏟 Jogo: {home} vs {away}\n"
    msg += f"🏆 Competição: {competition}\n"
    msg += f"⏱ Tempo: {minute}'\n"
    msg += f"⚽ Placar: {score}\n"
    msg += f"⛳ Escanteios: {fixture['corners']['home']} - {fixture['corners']['away']}\n"
    msg += f"➡ Detalhes: ⚠️ Entrada em ESCANTEIOS ASIÁTICOS\n"
    msg += f"https://www.bet365.com/#/AC/B1/C1/D13/E{fixture['fixture']['id']}/F2/"
    return msg

def evaluate_fixture(fixture):
    minute = fixture["fixture"]["status"]["elapsed"]
    corners_home = fixture["corners"]["home"]
    corners_away = fixture["corners"]["away"]

    # Estratégias: HT (33-38) e FT (83-87) alta chance 1-2 escanteios
    total_corners = corners_home + corners_away
    if 33 <= minute <= 38 and total_corners <= 2:
        return "HT - Alta Chance de Cantos"
    elif 83 <= minute <= 87 and total_corners <= 2:
        return "FT - Alta Chance de Cantos"
    return None

def monitor_loop():
    while True:
        try:
            fixtures = fetch_live_fixtures()
            for fix in fixtures:
                try:
                    strategy = evaluate_fixture(fix)
                    if strategy:
                        fixture_id = fix["fixture"]["id"]
                        key = f"{fixture_id}:{strategy}"
                        with lock:
                            if key in sent_signals:
                                continue
                            sent_signals.add(key)

                        msg = build_message(fix, strategy)
                        if TARGET_CHAT_ID:
                            bot.send_message(chat_id=int(TARGET_CHAT_ID), text=msg, parse_mode=ParseMode.MARKDOWN)
                        else:
                            print(msg)
                except Exception as e:
                    print("Erro avaliando partida:", e)
        except Exception as e:
            print("Erro no loop principal:", e)
        time.sleep(POLL_INTERVAL)

# -------------------------
# Webhook Flask
# -------------------------
@app.route(f"/{TELEGRAM_BOT_TOKEN}", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), bot)
    application.process_update(update)
    return "OK"

@app.route("/")
def index():
    return "Bot ESCANTEIOS RP ativo!"

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
    import threading

    # Inicia monitoramento em thread separada
    threading.Thread(target=monitor_loop, daemon=True).start()

    # Configura webhook no Telegram (substitua SEU_SERVICO pelo seu domínio do Render)
    URL = f"https://SEU_SERVICO.onrender.com/{TELEGRAM_BOT_TOKEN}"
    bot.delete_webhook()
    bot.set_webhook(URL)

    # Inicia Flask
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)