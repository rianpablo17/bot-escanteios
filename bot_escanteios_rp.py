# bot_escanteios_rp.py — webhook + sinais HT/FT de escanteios asiáticos

import os
import logging
import asyncio
from datetime import datetime
from flask import Flask, request
from telegram import Update, ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes

# -----------------------------
# CONFIGURAÇÃO DE LOG
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
WEBHOOK_URL = f"https://bot-escanteios17.onrender.com/{TOKEN}"

if not TOKEN:
    raise ValueError("⚠️ TOKEN não definido!")

# -----------------------------
# INICIALIZA O BOT
# -----------------------------
app = Flask(__name__)
application = Application.builder().token(TOKEN).build()

# -----------------------------
# VARIÁVEL GLOBAL PARA ARMAZENAR CHAT_ID
# -----------------------------
CHAT_ID = None

# -----------------------------
# HANDLERS DE COMANDOS
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
# FUNÇÃO DE ENVIO DE SINAIS
# -----------------------------
async def enviar_sinal(jogo, competicao, tempo, placar, cantos, odds, bet365_link, tipo):
    """
    Envia mensagem formatada de sinal de escanteio asiático.
    """
    global CHAT_ID
    if not CHAT_ID:
        logger.warning("❌ Chat ID não definido. Envie /id no grupo primeiro.")
        return

    mensagem = (
        f"📣 Alerta Estratégia: {tipo}\n"
        f"🏟 Jogo: {jogo}\n"
        f"🏆 Competição: {competicao}\n"
        f"🕛 Tempo: {tempo}\n"
        f"⚽ Placar: {placar}\n"
        f"⛳ Cantos: {cantos}\n"
        f"📈 Odds 1x2: {odds}\n"
        f"🔗 [Bet365]({bet365_link})\n"
        f"➡️ Detalhes: ⚠️ Entrar em ESCANTEIOS ASIÁTICOS conforme estratégia!"
    )

    await application.bot.send_message(chat_id=CHAT_ID, text=mensagem, parse_mode=ParseMode.MARKDOWN)
    logger.info(f"Sinal enviado: {mensagem}")

# -----------------------------
# FUNÇÃO DE SIMULAÇÃO DE DETECÇÃO DE SINAIS (HT/FT)
# -----------------------------
async def verificar_sinais_periodicamente():
    """
    Função simulada para enviar sinais automaticamente.
    Substitua esta função pelo feed real quando tiver os dados de jogos.
    """
    while True:
        # Exemplo de dados simulados
        jogos_simulados = [
            {
                "jogo": "Sweden (4º) x Kosovo (2º)",
                "competicao": "UEFA WC Qualification Europe",
                "tempo": "32'",
                "placar": "0 x 1 (0 x 1 Intervalo)",
                "cantos": "5 - 0 (1ºP: 5 - 0)",
                "odds": "1.33 / 5.5 / 8",
                "bet365_link": "https://bet365.bet.br/#/AX/K^Kosovo/",
                "tipo": "HT - Casa Perdendo"
            },
            {
                "jogo": "France x Germany",
                "competicao": "Friendly Match",
                "tempo": "84'",
                "placar": "2 x 1",
                "cantos": "8 - 5 (2ºP: 3 - 5)",
                "odds": "1.50 / 4.2 / 6.5",
                "bet365_link": "https://bet365.bet.br/#/AX/FranceGermany/",
                "tipo": "FT - Favorito Perdendo"
            }
        ]

        for jogo in jogos_simulados:
            await enviar_sinal(**jogo)

        await asyncio.sleep(60)  # verifica a cada 60 segundos (ajuste conforme necessário)

# -----------------------------
# ROTA RAIZ (TESTE)
# -----------------------------
@app.route("/", methods=["GET"])
def home():
    return "Bot de Escanteios rodando no Render! ✅"

# -----------------------------
# ROTA DO WEBHOOK (Telegram → Bot)
# -----------------------------
@app.route(f"/{TOKEN}", methods=["POST"])
def receive_update():
    """Recebe update do Telegram e processa corretamente os handlers."""
    update = Update.de_json(request.get_json(force=True), application.bot)
    import asyncio
    asyncio.run(application.update_queue.put(update))
    return "ok", 200

# -----------------------------
# INÍCIO
# -----------------------------
if __name__ == "__main__":
    logger.info("🚀 Iniciando bot com Flask + Webhook + sinais HT/FT...")
    # Start da verificação de sinais assíncrona
    asyncio.get_event_loop().create_task(verificar_sinais_periodicamente())

    application.run_webhook(
        listen="0.0.0.0",
        port=int(os.environ.get("PORT", 10000)),
        url_path=TOKEN,
        webhook_url=WEBHOOK_URL
    )
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))