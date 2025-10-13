# bot.py adaptado para Render (Flask + webhook)
import os
import requests
import traceback
from datetime import datetime

from flask import Flask, request
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ========== CONFIGURAÇÃO ==========
TOKEN = os.getenv("7977015488:AAFdpmpZE-6O0V-wIJnUa5UQu3Osil-lzEI")  # defina no Render
CHAT_ID = os.getenv("7400926391")  # defina no Render

API_KEY = os.getenv("d6fec5cd6cmsh108e41f6f563c21p140d1fjsnaee05756c8a8")  # API-Football
BASE_URL = "https://v3.football.api-sports.io"

POLL_INTERVAL = 15
N_LAST = 10
MIN_AVG_CORNERS = 9.0
HT_WINDOW = (30, 38)
FT_WINDOW = (80, 88)

SENT_SIGNALS = set()

headers = {
    "x-apisports-key": API_KEY,
    "Accept": "application/json"
}

# ========== UTILIDADES ==========
def enviar_mensagem(mensagem):
    if not TOKEN or not CHAT_ID:
        print("⚠️ Configure TELEGRAM_TOKEN e TELEGRAM_CHAT_ID no Render.")
        return
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    dados = {"chat_id": CHAT_ID, "text": mensagem, "parse_mode": "HTML"}
    try:
        resp = requests.post(url, data=dados, timeout=10)
        if not resp.ok:
            print(f"Erro ao enviar mensagem: HTTP {resp.status_code} - {resp.text}")
    except requests.exceptions.RequestException as e:
        print("Erro ao enviar mensagem:", e)
        traceback.print_exc()

def safe_get(url, params=None):
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=10)
        if resp.ok:
            return resp.json()
        else:
            print("Erro HTTP", resp.status_code, resp.text)
            return None
    except Exception as e:
        print("Exception safe_get:", e)
        return None

# (Aqui você copia todas as funções de dados e lógica do seu bot original: 
# get_live_fixtures, get_fixture_events, get_fixture_statistics, avg_corners_for_team,
# get_team_last_fixtures, get_team_position_in_league, build_bet365_link, evaluate_and_send_signals)
# Recomendo colar exatamente como estão, apenas removendo o loop while.

# ========== FLASK + TELEGRAM ==========
app = Flask(_name_)
application = Application.builder().token(TOKEN).build()

# Exemplo comando /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚀 Bot de Escanteios está online!")

application.add_handler(CommandHandler("start", start))

# Home simples
@app.route("/")
def home():
    return "Bot de Escanteios ativo! ✅"

# Webhook
@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), application.bot)
    application.update_queue.put_nowait(update)
    # Avaliar sinais a cada requisição
    try:
        from threading import Thread
        Thread(target=evaluate_and_send_signals).start()
    except Exception as e:
        print("Erro no evaluate_and_send_signals via webhook:", e)
    return "OK", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)