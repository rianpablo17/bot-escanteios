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
    msg += f"⚽ Placar: {score