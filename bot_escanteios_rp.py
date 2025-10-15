# bot_escanteios_rp.py — versão corrigida com Flask + Webhook

import os
import logging
from flask import Flask, request
from telegram import Update
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
    raise ValueError("⚠️ TOKEN não definido! Configure a variável de ambiente 'TOKEN' no Render.")

# -----------------------------
# INICIALIZA O BOT
# -----------------------------
app = Flask(__name__)
application = Application.builder().token(TOKEN).build()

# -----------------------------
# HANDLERS DE COMANDOS
# -----------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚀 Bot de Escanteios Ativo! Pronto para detectar sinais ao vivo!")

application.add_handler(CommandHandler("start", start))

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
    update = Update.de_json(request.get_json(force=True), application.bot)
    application.update_queue.put(update)
    return "ok", 200

# -----------------------------
# INÍCIO
# -----------------------------
if __name__ == "__main__":
    logger.info("🚀 Iniciando bot com Flask + Webhook...")
    application.run_webhook(
        listen="0.0.0.0",
        port=int(os.environ.get("PORT", 10000)),
        url_path=TOKEN,
        webhook_url=WEBHOOK_URL
    )
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))