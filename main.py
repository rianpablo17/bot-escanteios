# main.py

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import logging

# Configuração do logging para rastrear erros
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Token do bot (substitua pelo seu token real)
TOKEN = "7977015488:AAGuGOSA6TfQeH-wrhacIr6Tj1EYW3CXPg4"

# Função para o comando /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Olá! Bot de escanteios ativado! 🚀")

# Função para o comando /help
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Use este bot para receber notificações de escanteios.")

# Função principal para rodar o bot
def main():
    # Cria a aplicação do bot
    app = ApplicationBuilder().token(TOKEN).build()

    # Adiciona os handlers de comando
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))

    # Inicia o bot
    print("Bot iniciado...")
    app.run_polling()

# Ponto de entrada do script
if __name__ == "__main__":
    main()