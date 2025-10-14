import os
import time
import requests
import threading
from dotenv import load_dotenv
from flask import Flask, request
from telegram import Bot, Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("7977015488:AAHwZgsAy8lcLBYpB2yWSQcx5UD8JW5wUtM")
API_FOOTBALL_KEY = os.getenv("9426245bc61c633580ac7d46c391ba59")
TARGET_CHAT_ID = os.getenv("TARGET_CHAT_ID")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", 30))  # tempo de checagem em segundos

bot = Bot(token=TELEGRAM_BOT_TOKEN)
app = Flask(_name_)

sent_signals = set()
lock = threading.Lock()
API_BASE = "https://v3.football.api-sports.io"
HEADERS = {"x-apisports-key": API_FOOTBALL_KEY}

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
    r = requests.get(url, headers=HEADERS, timeout=10)
    data = r.json()
    return data.get("response", [])

def fetch_fixture_statistics(fixture_id):
    url = f"{API_BASE}/fixtures/statistics?fixture={fixture_id}"
    r = requests.get(url, headers=HEADERS, timeout=10)
    data = r.json()
    return data.get("response", [])

def build_message(fixture, strategy):
    home = fixture["teams"]["home"]["name"]
    away = fixture["teams"]["away"]["name"]
    score = f'{fixture["goals"]["home"]} x {fixture["goals"]["away"]}'
    minute = fixture["fixture"]["status"]["elapsed"]
    competition = fixture["league"]["name"]

    # Mensagem com layout diferente do original
    msg = f"🚩 Alerta Estratégia: {strategy}\n"
    msg += f"🏟 Jogo: {home} vs {away}\n"
    msg += f"🏆 Competição: {competition}\n"
    msg += f"⏱ Tempo: {minute} '\n"
    msg += f"⚽ Placar: {score}\n"
    msg += f"⛳ Escanteios: {fixture['corners']['home']} - {fixture['corners']['away']}\n"
    msg += f"➡ Detalhes: ⚠️ Entrada em ESCANTEIOS ASIÁTICOS\n"
    msg += f"https://www.bet365.com/#/AC/B1/C1/D13/E{fixture['fixture']['id']}/F2/"
    return msg

def evaluate_fixture(fixture):
    # Estrutura simplificada de exemplo:
    # Estratégia HT: minuto 33-38, alta chance 1-2 escanteios
    # Estratégia FT: minuto 83-87, alta chance 1-2 escanteios
    minute = fixture["fixture"]["status"]["elapsed"]
    corners_home = fixture["corners"]["home"]
    corners_away = fixture["corners"]["away"]

    if 33 <= minute <= 38 and (corners_home + corners_away) <= 2:
        return "HT - Alta Chance de Cantos"
    elif 83 <= minute <= 87 and (corners_home + corners_away) <= 2:
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
                            bot.send_message(chat_id=int(TARGET_CHAT_ID), text=msg, parse_mode="Markdown")
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

    # Configura webhook no Telegram
    URL = f"https://SEU_SERVICO.onrender.com/{TELEGRAM_BOT_TOKEN}"  # substitua aqui
    bot.delete_webhook()
    bot.set_webhook(URL)

    # Inicia Flask
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)