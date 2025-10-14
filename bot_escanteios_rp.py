# BOT_ESCANTEIOS_RP - bot.py (Atualizado com comando /id)
# --------------------------------------------------
# INSTRUÇÕES:
# 1) Salve este arquivo como bot_escanteios_rp.py
# 2) Crie um arquivo chamado .env no mesmo diretório com as variáveis abaixo:
#
#   TELEGRAM_BOT_TOKEN=seu_token_do_telegram_aqui
#   API_FOOTBALL_KEY=9426245bc61c633580ac7d46c391ba59
#   TARGET_CHAT_ID=-100XXXXXXXXXX
#   POLL_INTERVAL=30
#
# 3) Instale dependências:
#    pip install python-dotenv requests python-telegram-bot==13.15
#
# 4) Execute:
#    python bot_escanteios_rp.py
#
# --------------------------------------------------

import os
import time
import requests
import threading
from dotenv import load_dotenv
from telegram import Bot, ParseMode
from telegram.ext import Updater, CommandHandler

load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
API_FOOTBALL_KEY = os.getenv('API_FOOTBALL_KEY')
TARGET_CHAT_ID = os.getenv('TARGET_CHAT_ID')
POLL_INTERVAL = int(os.getenv('POLL_INTERVAL', 30))

if not API_FOOTBALL_KEY:
    raise RuntimeError('API_FOOTBALL_KEY não encontrado no .env')

bot = None
if TELEGRAM_BOT_TOKEN:
    bot = Bot(token=TELEGRAM_BOT_TOKEN)

API_BASE = 'https://v3.football.api-sports.io'
HEADERS = {'x-apisports-key': API_FOOTBALL_KEY}

sent_signals = set()
lock = threading.Lock()

# Comando /start
def start(update, context):
    update.message.reply_text('BOT_ESCANTEIOS RP™ está ativo! Use /id para descobrir o chat_id do grupo.')

# Novo comando /id para pegar chat_id
def get_chat_id(update, context):
    chat = update.effective_chat
    update.message.reply_text(f'📋 ID do Grupo: {chat.id}')

# Funções auxiliares (fetch_live_fixtures, fetch_fixture_statistics, get_stat, build_message, evaluate_fixture, send_signal)
# ... (mesmo código da versão anterior, mantido para monitoramento e envio de sinais) ...

# Main loop: busca partidas e avalia
def monitor_loop(target_chat_id):
    print('Iniciando monitoramento (poll interval =', POLL_INTERVAL, 's)')
    while True:
        try:
            fixtures = fetch_live_fixtures()
            for fix in fixtures:
                try:
                    result = evaluate_fixture(fix)
                    if result:
                        strategy, fdata = result
                        fixture_id = fdata.get('fixture', {}).get('id')
                        minute = fdata.get('fixture', {}).get('status', {}).get('elapsed')
                        key = f"{fixture_id}:{strategy}:{minute}"
                        with lock:
                            if key in sent_signals:
                                continue
                            sent_signals.add(key)

                        label = 'HT - Alta Chance de Cantos' if strategy == 'HT' else ('FT - Alta Chance de Cantos' if strategy == 'FT' else 'Alta Chance de Cantos')
                        msg = build_message(fdata, label)
                        if target_chat_id:
                            send_signal(target_chat_id, msg)
                        else:
                            print(msg)
                except Exception as e:
                    print('Erro avaliando partida:', e)
        except Exception as e:
            print('Erro no loop principal:', e)
        time.sleep(POLL_INTERVAL)

# Setup Telegram handlers
def run_telegram_bot_and_monitor():
    target_chat_id = int(TARGET_CHAT_ID) if TARGET_CHAT_ID else None

    updater = None
    if TELEGRAM_BOT_TOKEN:
        updater = Updater(token=TELEGRAM_BOT_TOKEN, use_context=True)
        dp = updater.dispatcher
        dp.add_handler(CommandHandler('start', start))
        dp.add_handler(CommandHandler('id', get_chat_id))  # novo comando /id
        updater.start_polling()
        print('Telegram polling iniciado. Use /id no grupo para obter o chat_id.')

    monitor_loop(target_chat_id)

if __name_== '__main__':
    run_telegram_bot_and_monitor()