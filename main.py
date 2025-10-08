import os
import requests
from telegram import Bot
from flask import Flask
from datetime import datetime
import time

# =========================
# CONFIGURAÇÕES DO BOT
# =========================
TELEGRAM_TOKEN = "7977015488:AAFdpmpZE-6O0V-wIJnUa5UQu3Osil-lzEI"
CHAT_ID = "7400926391"
API_KEY = "d6fec5cd6cmsh108e41f6f563c21p140d1fjsnaee05756c8a8"

bot = Bot(token=TELEGRAM_TOKEN)

# =========================
# FUNÇÕES PRINCIPAIS
# =========================
def enviar_mensagem(texto):
    """Envia mensagem para o Telegram"""
    try:
        bot.send_message(chat_id=CHAT_ID, text=texto)
        print(f"✅ Mensagem enviada: {texto}")
    except Exception as e:
        print(f"❌ Erro ao enviar mensagem: {e}")

def buscar_dados_escanteios():
    """Simula captura de dados de escanteios da API"""
    # Aqui você insere seu código real para pegar dados da API
    # Exemplo genérico:
    dados = {
        "time_casa": "Time A",
        "time_fora": "Time B",
        "escanteios": 10,
        "tempo": 55
    }
    return dados

def processar_jogo():
    """Processa os dados e envia notificação se necessário"""
    jogo = buscar_dados_escanteios()
    mensagem = (
        f"📊 Oportunidade de Escanteios!\n"
        f"{jogo['time_casa']} x {jogo['time_fora']}\n"
        f"Escanteios: {jogo['escanteios']}\n"
        f"Minuto: {jogo['tempo']}'"
    )
    enviar_mensagem(mensagem)

# =========================
# INICIO DO BOT
# =========================
enviar_mensagem("🤖 Bot iniciado com sucesso! Rodando no Render gratuito.")

# =========================
# LOOP PRINCIPAL (simulação)
# =========================
def loop_principal():
    while True:
        try:
            processar_jogo()
            time.sleep(60)  # espera 1 minuto antes de verificar novamente
        except Exception as e:
            print(f"❌ Erro no loop principal: {e}")
            time.sleep(60)

# =========================
# CONFIGURAÇÃO DE PORTA PARA RENDER
# =========================
app = Flask(_name_)

@app.route("/")
def home():
    return "Bot rodando!"

if _name_ == "_main_":
    import threading

    # Roda o bot em thread separada
    bot_thread = threading.Thread(target=loop_principal)
    bot_thread.start()

    # Roda o Flask só pra abrir porta
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)