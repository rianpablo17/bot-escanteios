import os
import requests
from telegram import _version_ as ptb_version
from telegram import Bot
from telegram.ext import ApplicationBuilder
from flask import Flask
import asyncio
import threading
import time

print(f"🔹 Rodando python-telegram-bot versão {ptb_version}")

# =========================
# CONFIGURAÇÕES DO BOT
# =========================
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
API_KEY = os.environ.get("API_KEY")

bot = Bot(token=TELEGRAM_TOKEN)

# =========================
# FUNÇÕES PRINCIPAIS
# =========================
async def enviar_mensagem(texto):
    """Envia mensagem para o Telegram"""
    try:
        await bot.send_message(chat_id=CHAT_ID, text=texto)
        print(f"✅ Mensagem enviada: {texto}")
    except Exception as e:
        print(f"❌ Erro ao enviar mensagem: {e}")

def buscar_dados_escanteios():
    """Simula captura de dados de escanteios da API"""
    dados = {
        "time_casa": "Time A",
        "time_fora": "Time B",
        "escanteios": 10,
        "tempo": 55
    }
    print(f"🔹 Dados recebidos: {dados}")
    return dados

async def processar_jogo():
    """Processa os dados e envia notificação se necessário"""
    jogo = buscar_dados_escanteios()
    mensagem = (
        f"📊 Oportunidade de Escanteios!\n"
        f"{jogo['time_casa']} x {jogo['time_fora']}\n"
        f"Escanteios: {jogo['escanteios']}\n"
        f"Minuto: {jogo['tempo']}'"
    )
    await enviar_mensagem(mensagem)

# =========================
# LOOP PRINCIPAL
# =========================
async def loop_principal():
    while True:
        try:
            await processar_jogo()
            await asyncio.sleep(60)  # espera 1 minuto
        except Exception as e:
            print(f"❌ Erro no loop principal: {e}")
            await asyncio.sleep(60)

# =========================
# CONFIGURAÇÃO DE PORTA PARA RENDER
# =========================
app = Flask(_name_)

@app.route("/")
def home():
    return "Bot rodando!"

if _name_ == "_main_":
    # Roda o Flask numa thread separada
    threading.Thread(target=lambda: app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))).start()
    # Roda o loop principal de forma assíncrona
    asyncio.run(loop_principal())