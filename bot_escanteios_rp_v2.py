"""
bot_escanteios_rp_v2_fixed.py
Versão estável com webhook funcional e envio de sinais ao Telegram (sem erro 404)
"""

import os
import time
import math
import requests
import logging
from datetime import datetime
from collections import defaultdict
from threading import Thread
from flask import Flask, request
from telegram import Bot, Update
from telegram.ext import Application, ContextTypes, CommandHandler

# ---------------------- CONFIG ----------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
API_KEY = os.getenv("API_FOOTBALL_KEY")
BASE_URL = os.getenv("URL_PUBLICA") or "https://bot-escanteios17.onrender.com"  # altere se seu app tiver outro domínio
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "20"))

HT_WINDOW_MIN_START = 35
HT_WINDOW_MIN_END = 45
FT_WINDOW_MIN_START = 80
FT_WINDOW_MIN_END = 90
PROB_THRESHOLD_HIGH = 0.70
PROB_THRESHOLD_2C = 0.65

priority_leagues = {}
small_stadiums = [
    'loftus road', 'vitality stadium', 'kenilworth road',
    'turf moor', 'crowd', 'bramall lane', 'ewood park',
]

sent_signals = defaultdict(set)
API_BASE = "https://v3.football.api-sports.io"
HEADERS = {"x-apisports-key": API_KEY}

# ---------------------- HELPERS ----------------------

def send_telegram_message(text, parse_mode='HTML'):
    if not TOKEN or not CHAT_ID:
        logger.warning("Token ou Chat ID não configurados.")
        return
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": parse_mode, "disable_web_page_preview": False}
        r = requests.post(url, data=payload, timeout=10)
        if r.status_code != 200:
            logger.warning("Erro Telegram: %s %s", r.status_code, r.text)
    except Exception as e:
        logger.exception("Falha ao enviar mensagem: %s", e)


def get_live_fixtures():
    try:
        r = requests.get(f"{API_BASE}/fixtures?live=all", headers=HEADERS, timeout=10)
        if r.status_code == 200:
            return r.json().get("response", [])
    except Exception as e:
        logger.error("Erro ao buscar fixtures: %s", e)
    return []


def get_fixture_statistics(fixture_id):
    try:
        r = requests.get(f"{API_BASE}/fixtures/statistics?fixture={fixture_id}", headers=HEADERS, timeout=10)
        if r.status_code == 200:
            return r.json().get("response", [])
    except Exception as e:
        logger.error("Erro ao buscar estatísticas: %s", e)
    return []


def get_standings(league_id, season, team_id):
    try:
        r = requests.get(f"{API_BASE}/standings?league={league_id}&season={season}", headers=HEADERS, timeout=10)
        if r.status_code == 200:
            for entry in r.json().get("response", []):
                for team in entry.get("league", {}).get("standings", [[]])[0]:
                    if team["team"]["id"] == team_id:
                        return team
    except Exception:
        return None


def poisson_prob_ge(k, lam):
    prob_lt_k = sum(math.exp(-lam) * (lam ** i) / math.factorial(i) for i in range(k))
    return max(0.0, 1.0 - prob_lt_k)


def estimate_probability_of_corners(minutes_remaining, total_corners, minute):
    rate = total_corners / minute if minute > 0 else 0.06
    lam = rate * minutes_remaining
    p_ge_1 = poisson_prob_ge(1, lam)
    p_ge_2 = poisson_prob_ge(2, lam)
    return lam, p_ge_1, p_ge_2


def is_small_stadium(venue_name):
    if not venue_name:
        return False
    name = venue_name.lower()
    return any(s in name for s in small_stadiums)


def build_signal_text(fixture, window_key, metrics):
    league = fixture["league"]
    teams = fixture["teams"]
    fixture_info = fixture["fixture"]
    minute = metrics.get("minute", 0)
    home = teams["home"]["name"]
    away = teams["away"]["name"]
    score = f"{fixture.get('goals', {}).get('home', '-')} x {fixture.get('goals', {}).get('away', '-')}"
    venue = fixture_info.get("venue", {}).get("name", "Desconhecido")

    season = league.get("season")
    home_pos = get_standings(league.get("id"), season, teams["home"]["id"])
    away_pos = get_standings(league.get("id"), season, teams["away"]["id"])

    pos_text = f"{home} (#{home_pos.get('rank','-')}) x {away} (#{away_pos.get('rank','-')})" if home_pos and away_pos else f"{home} x {away}"
    tempo_extra = " + " + str(round((metrics.get('lam', 0) * 10) / 6, 1)) + " min (estimado)"  # base de acréscimo estimada

    link_bet365 = f"https://www.bet365.com/#/AX/K%5E{league.get('id')}/"  # link genérico, liga ID

    txt = f"""
🚨 <b>SINAL {window_key} - ESCANTEIOS</b> 🚨
<b>Partida:</b> {pos_text}
<b>Competição:</b> {league.get('name')}
<b>Minuto:</b> {minute}{tempo_extra}
<b>Placar:</b> {score}
<b>Cantos:</b> {metrics.get('total_corners')} (H: {metrics.get('home_corners')} - A: {metrics.get('away_corners')})
<b>Prob ≥1:</b> {metrics.get('p_ge_1')*100:.0f}% | <b>Prob ≥2:</b> {metrics.get('p_ge_2')*100:.0f}%
<b>Estádio:</b> {venue} {'✅' if metrics.get('small_stadium') else '❌'}
<b>🔗 Bet365:</b> {link_bet365}

<b>Obs:</b> janela {window_key}, escanteios asiáticos 1–2
    """
    return txt.strip()


def compute_match_score(fixture):
    fixture_id = fixture["fixture"]["id"]
    league = fixture["league"]
    teams = fixture["teams"]
    venue = fixture["fixture"].get("venue", {})
    event_minute = fixture["fixture"]["status"].get("elapsed") or 0
    stats = get_fixture_statistics(fixture_id)

    home_corners = away_corners = 0
    for team_stats in stats:
        if team_stats.get("statistics"):
            for s in team_stats["statistics"]:
                if s.get("type", "").lower() in ("corners", "corner kicks"):
                    val = s.get("value", 0)
                    if team_stats["team"]["id"] == teams["home"]["id"]:
                        home_corners = val
                    else:
                        away_corners = val

    total_corners = home_corners + away_corners
    small = is_small_stadium(venue.get("name"))
    league_weight = priority_leagues.get(league.get("id"), 0)

    results = {}
    for key, (start, end) in {"HT": (HT_WINDOW_MIN_START, HT_WINDOW_MIN_END), "FT": (FT_WINDOW_MIN_START, FT_WINDOW_MIN_END)}.items():
        if start <= event_minute <= end:
            rem = end - event_minute
            lam, p1, p2 = estimate_probability_of_corners(rem, total_corners, event_minute)
            p1 = min(1.0, p1 + league_weight + (0.15 if small else 0))
            p2 = min(1.0, p2 + league_weight + (0.15 if small else 0))
            results[key] = {"minute": event_minute, "home_corners": home_corners, "away_corners": away_corners, "total_corners": total_corners, "p_ge_1": p1, "p_ge_2": p2, "lam": lam, "small_stadium": small}
    return results


def process_fixtures_and_send():
    fixtures = get_live_fixtures()
    if not fixtures:
        logger.info("Sem partidas ao vivo.")
        return

    for fixture in fixtures:
        fixture_id = fixture["fixture"]["id"]
        metrics_per_window = compute_match_score(fixture)
        for window_key, metrics in metrics_per_window.items():
            send_for_1 = metrics["p_ge_1"] >= PROB_THRESHOLD_HIGH
            send_for_2 = metrics["p_ge_2"] >= PROB_THRESHOLD_2C
            already_sent = f"{window_key}:{'2' if send_for_2 else '1'}"

            if (send_for_1 or send_for_2) and already_sent not in sent_signals[fixture_id]:
                text = build_signal_text(fixture, window_key, metrics)
                send_telegram_message(text)
                sent_signals[fixture_id].add(already_sent)
                logger.info("✅ Sinal enviado: %s (%s)", fixture_id, window_key)


def start_loop():
    while True:
        try:
            process_fixtures_and_send()
        except Exception as e:
            logger.error("Erro no loop: %s", e)
        time.sleep(POLL_INTERVAL)

# ---------------------- FLASK & WEBHOOK ----------------------
app = Flask(__name__)

@app.route("/healthz")
def health():
    return "ok", 200

@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    return "ok", 200  # apenas para não retornar 404 ao Telegram

# ---------------------- MAIN ----------------------
if __name__ == "__main__":
    Thread(target=start_loop, daemon=True).start()
    port = int(os.getenv("PORT", "10000"))
    logger.info(f"🌐 Webhook ativo: {BASE_URL}/{TOKEN}")
    app.run(host="0.0.0.0", port=port)