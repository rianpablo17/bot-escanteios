# bot.py - Bot de escanteios pronto para Render

import os
import logging
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
CHAT_ID = os.getenv("CHAT_ID")  # Opcional, se quiser enviar mensagens automáticas

if not TOKEN:
    raise ValueError("⚠️ TOKEN não definido! Configure a variável de ambiente 'TOKEN' no Render.")

if CHAT_ID:
    try:
        CHAT_ID = int(CHAT_ID)
    except ValueError:
        raise ValueError("⚠️ CHAT_ID inválido! Deve ser um número inteiro.")

# -----------------------------
# HANDLERS
# -----------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Responde ao comando /start"""
    await update.message.reply_text("Olá! Bot de escanteios ativo 🚀")

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Exemplo: ecoa a mensagem recebida"""
    await update.message.reply_text(f"Você disse: {update.message.text}")

# -----------------------------
# FUNÇÃO PRINCIPAL
# -----------------------------
def main():
    # Cria a aplicação do bot
    application = Application.builder().token(TOKEN).build()

    # Adiciona comandos
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("echo", echo))

    # Inicia o bot
    logger.info("Bot iniciado com sucesso 🚀")
    application.run_polling()

if __name__ == "__main__":
    main()