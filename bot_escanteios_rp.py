# bot_escanteios_rp.py — sinais HT/FT de escanteios asiáticos ao vivo com API-Football

import os
import logging
import asyncio
import requests
from flask import Flask, request
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes

# -----------------------------
# LOG
# -----------------------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# -----------------------------
# VARIÁVEIS DE AMBIENTE
# -----------------------------
TOKEN = os.getenv("TOKEN")
API_FOOTBALL_KEY = os.getenv("API_FOOTBALL_KEY")
WEBHOOK_URL = f"https://bot-escanteios17.onrender.com/{TOKEN}"

if not TOKEN or not API_FOOTBALL_KEY:
    raise ValueError("⚠️ Variáveis TOKEN ou API_FOOTBALL_KEY não definidas!")

# -----------------------------
# BOT E FLASK
# -----------------------------
app = Flask(__name__)
application = Application.builder().token(TOKEN).build()
CHAT_ID = None

# -----------------------------
# COMANDOS
# -----------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚀 Bot de Escanteios Ativo! Pronto para detectar sinais ao vivo!")

async def get_chat_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global CHAT_ID
    CHAT_ID = update.effective_chat.id
    await update.message.reply_text(f"✅ Chat ID deste chat salvo!\nID: {CHAT_ID}")
    logger.info(f"Chat ID capturado: {CHAT_ID}")

application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("id", get_chat_id))

# -----------------------------
# FUNÇÕES DE API-Football
# -----------------------------
def obter_jogos_ao_vivo():
    url = "https://v3.football.api-sports.io/fixtures"
    headers = {"x-apisports-key": API_FOOTBALL_KEY}
    params = {"live": "all"}
    response = requests.get(url, headers=headers, params=params)
    if response.status_code == 200:
        return response.json().get("response", [])
    else:
        logger.error(f"Erro API-Football: {response.status_code}")
        return []

# -----------------------------
# ANALISADOR DE SINAIS
# -----------------------------
def analisar_sinal(jogo):
    """
    Detecta sinais HT/FT de escanteios asiáticos
    """
    fixture = jogo["fixture"]
    score = jogo["score"]
    elapsed = score.get("elapsed", 0)
    home_goals = score["halftime"]["home"] if score.get("halftime") else 0
    away_goals = score["halftime"]["away"] if score.get("halftime") else 0

    # Estratégia HT (33-38')
    if 33 <= elapsed <= 38 and home_goals < away_goals:
        return "HT - Casa Perdendo"
    # Estratégia FT (83-87')
    if 83 <= elapsed <= 87 and home_goals < away_goals:
        return "FT - Favorito Perdendo"
    return None

# -----------------------------
# FORMATAÇÃO DE MENSAGEM
# -----------------------------
def formatar_mensagem(jogo, tipo):
    fixture = jogo["fixture"]
    league = jogo["league"]["name"]
    teams = jogo["teams"]
    score = jogo["score"]
    elapsed = score.get("elapsed", 0)
    placar = f"{score['fulltime']['home']} x {score['fulltime']['away']}"
    cantos = "—"  # Placeholder: depois pode colocar corners reais
    odds = "—"    # Placeholder: depois integra Odds API

    return (
        f"📣 Alerta Estratégia: {tipo}\n"
        f"🏟 Jogo: {teams['home']['name']} x {teams['away']['name']}\n"
        f"🏆 Competição: {league}\n"
        f"🕛 Tempo: {elapsed}'\n"
        f"⚽ Placar: {placar}\n"
        f"⛳ Cantos: {cantos}\n"
        f"📈 Odds 1x2: {odds}\n"
        f"🔗 [Bet365](https://www.bet365.com/#/AC/B1/C1/D13/E12345/F123/)\n"
        f"➡️ Detalhes:  👉 Fazer a entrada em ESCANTEIOS ASIÁTICOS ⚠️ CANTO OU GOL PARA O FAVORITO ANTES DE ABRIR O ASIÁTICO RECOMENDANDO \"ABORTAR\""
    )

# -----------------------------
# ENVIO DE SINAIS
# -----------------------------
async def enviar_sinais_ao_vivo():
    while True:
        jogos = obter_jogos_ao_vivo()
        for jogo in jogos:
            tipo = analisar_sinal(jogo)
            if tipo and CHAT_ID:
                mensagem = formatar_mensagem(jogo, tipo)
                await application.bot.send_message(chat_id=CHAT_ID, text=mensagem, parse_mode=ParseMode.MARKDOWN)
                logger.info(f"Sinal enviado: {mensagem}")
        await asyncio.sleep(30)  # verifica a cada 30s

# -----------------------------
# FLASK WEBHOOK
# -----------------------------
@app.route("/", methods=["GET"])
def home():
    return "Bot de Escanteios rodando no Render! ✅"

@app.route(f"/{TOKEN}", methods=["POST"])
def receive_update():
    update = Update.de_json(request.get_json(force=True), application.bot)
    import asyncio
    asyncio.run(application.update_queue.put(update))
    return "ok", 200

# -----------------------------
# INÍCIO 
# -----------------------------
if __name__ == "__main__":
    logger.info("🚀 Iniciando bot com Flask + Webhook + sinais ao vivo HT/FT...")

    # Inicia a task de sinais ao vivo
    asyncio.get_event_loop().create_task(enviar_sinais_ao_vivo())

    # Apenas webhook do Telegram (Flask já incluso)
    application.run_webhook(
        listen="0.0.0.0",
        port=int(os.environ.get("PORT", 10000)),
        url_path=TOKEN,
        webhook_url=WEBHOOK_URL
    )