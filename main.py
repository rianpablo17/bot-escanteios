# =========================
# 🤖 BOT DE ESCANTEIOS - VERSÃO LIMPA E ESTÁVEL
# =========================

import requests
import time

# =========================
# 🔧 CONFIGURAÇÕES DO BOT
# =========================
TELEGRAM_TOKEN = "7977015488:AAFdpmpZE-6O0V-wIJnUa5UQu3Osil-lzEI"
CHAT_ID = "7400926391"
API_KEY = "d6fec5cd6cmsh108e41f6f563c21p140d1fjsnaee05756c8a8"

# =========================
# 🚀 INÍCIO DO BOT
# =========================
print("🤖 Bot iniciado com sucesso! Aguardando novos dados...")

# =========================
# 📤 FUNÇÃO PARA ENVIAR MENSAGEM NO TELEGRAM
# =========================
def enviar_mensagem(texto):
    """Envia uma mensagem para o chat configurado no Telegram."""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": texto}
    try:
        response = requests.post(url, json=payload)
        if response.status_code == 200:
            print("✅ Mensagem enviada com sucesso!")
        else:
            print(f"⚠️ Erro ao enviar mensagem: {response.text}")
    except Exception as e:
        print(f"❌ Exceção ao enviar mensagem: {e}")

# =========================
# ⚽ FUNÇÃO PARA BUSCAR DADOS DE ESCANTEIOS
# =========================
def buscar_dados_escanteios():
    """Busca dados na API e retorna os jogos que atendem aos critérios."""
    url = "https://api-football-v1.p.rapidapi.com/v3/fixtures"
    headers = {
        "x-rapidapi-key": API_KEY,
        "x-rapidapi-host": "api-football-v1.p.rapidapi.com"
    }
    params = {"live": "all"}  # Busca todos os jogos ao vivo

    try:
        resposta = requests.get(url, headers=headers, params=params, timeout=10)
        dados = resposta.json()
        jogos = dados.get("response", [])

        lista_jogos = []
        for jogo in jogos:
            try:
                casa = jogo["teams"]["home"]["name"]
                fora = jogo["teams"]["away"]["name"]
                escanteios_casa = jogo["statistics"][0]["statistics"][8]["value"]
                escanteios_fora = jogo["statistics"][1]["statistics"][8]["value"]
                total = escanteios_casa + escanteios_fora
                tempo = jogo["fixture"]["status"]["elapsed"]

                if total >= 8 and tempo <= 70:  # Critério de alerta
                    lista_jogos.append(
                        f"{casa} x {fora} ⚽\nEscanteios: {total}\nMinuto: {tempo}'"
                    )

            except Exception:
                continue  # Ignora jogos com dados faltando

        return lista_jogos

    except Exception as erro:
        print(f"❌ Erro ao buscar dados: {erro}")
        return []

# =========================
# 🔁 LOOP PRINCIPAL DO BOT
# =========================
try:
    while True:
        print("🔍 Verificando novos jogos...")
        jogos = buscar_dados_escanteios()

        if jogos:
            for jogo in jogos:
                enviar_mensagem(f"📊 Oportunidade de Escanteios:\n{jogo}")
        else:
            print("⏳ Nenhum jogo com critérios encontrados no momento.")

        time.sleep(60)  # Aguarda 1 minuto antes de buscar novamente

except Exception as e:
    print(f"🚨 Erro geral no bot: {e}")