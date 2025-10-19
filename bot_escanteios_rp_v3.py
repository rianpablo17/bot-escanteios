#!/usr/bin/env python3
# -- coding: utf-8 --
"""
bot_escanteios_rp_vip_plus_final_v2.py
Versão ULTRA PRO FINAL — otimizada para sinais HT/FT de cantos asiáticos.

Requisitos:
- Python 3.8+
- pip install requests flask

Environment variables required:
- API_FOOTBALL_KEY
- TOKEN
- TELEGRAM_CHAT_ID
- WEBHOOK_URL (opcional, não obrigatório para envio de mensagens)
"""

import os
import time
import math
import logging
from collections import defaultdict
from typing import Dict, Any, List, Tuple
import requests
from flask import Flask, jsonify

# ---------- CONFIG ----------
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO').upper()
logging.basicConfig(level=LOG_LEVEL, format='%(asctime)s %(levelname)s:%(name)s: %(message)s')
logger = logging.getLogger('bot_escanteios_vip_plus')

API_FOOTBALL_KEY = os.getenv('API_FOOTBALL_KEY')
TOKEN = os.getenv('TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
WEBHOOK_URL = os.getenv('WEBHOOK_URL')

API_BASE = "https://v3.football.api-sports.io"
HEADERS = {"x-apisports-key": API_FOOTBALL_KEY} if API_FOOTBALL_KEY else {}

HT_WINDOW = (35, 40)
FT_WINDOW = (80, 90)

PROB_LINE_THRESHOLD = 0.60
PROB_PUSH_ALERT = 0.20
MIN_PRESSURE_SCORE = 0.5

ATTACKS_MIN = 5
ATTACKS_DIFF = 4
DANGER_MIN = 5
DANGER_DIFF = 3

PRIORITY_LEAGUES = {39:0.05, 78:0.05, 140:0.04, 61:0.04, 135:0.03}
SMALL_STADIUMS = ['loftus road','vitality stadium','kenilworth road','turf moor','crowd','bramall lane','ewood park']

sent_signals = defaultdict(set)  # fixture_id -> set of keys

# ---------- FLASK HEALTH ----------
app = Flask(__name__)
@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'})

# ---------- POISSON HELPERS ----------
def poisson_pmf(k, lam):
    try:
        return (lam**k) * math.exp(-lam) / math.factorial(k) if k>=0 else 0.0
    except:
        return 0.0

def poisson_cdf_le(k, lam):
    s = 0.0
    for i in range(0, int(k)+1):
        s += poisson_pmf(i, lam)
    return s

def poisson_tail_ge(k, lam):
    return 1.0 if k<=0 else 1.0 - poisson_cdf_le(k-1, lam)

# ---------- API HELPERS ----------
def get_live_fixtures() -> List[Dict[str, Any]]:
    if not API_FOOTBALL_KEY:
        logger.error('API_FOOTBALL_KEY não definida.')
        return []
    try:
        r = requests.get(f"{API_BASE}/fixtures?live=all", headers=HEADERS, timeout=10)
        if r.status_code == 200:
            fixtures = r.json().get('response', [])
            logger.info('Fixtures ao vivo encontradas: %d', len(fixtures))
            return fixtures
        else:
            logger.warning('Status %s ao buscar fixtures: %.200s', r.status_code, r.text)
    except Exception as e:
        logger.exception('Erro ao buscar fixtures: %s', e)
    return []

def get_fixture_statistics(fixture_id):
    try:
        r = requests.get(f"{API_BASE}/fixtures/statistics?fixture={fixture_id}", headers=HEADERS, timeout=10)
        if r.status_code == 200:
            return r.json().get('response', [])
    except Exception as e:
        logger.exception('Erro ao buscar statistics: %s', e)
    return []

# ---------- STAT EXTRACTION ----------
def extract_basic_stats(fixture, stats_resp) -> Tuple[Dict[str,int], Dict[str,int]]:
    teams = fixture['teams']
    home_id = teams['home']['id']
    away_id = teams['away']['id']

    home = {'corners':0,'attacks':0,'danger':0}
    away = {'corners':0,'attacks':0,'danger':0}

    for entry in stats_resp:
        team = entry.get('team', {})
        stats_list = entry.get('statistics', []) or []
        target = home if team.get('id') == home_id else away
        for s in stats_list:
            t = str(s.get('type','')).lower()
            val = s.get('value') or 0
            try: val = int(float(str(val).replace('%','')))
            except: val = 0
            if 'corner' in t: target['corners']=val
            elif 'attack' in t and 'danger' not in t: target['attacks']=val
            elif 'on goal' in t or 'danger' in t or 'shots on goal' in t: target['danger']=val
    return home, away

# ---------- PRESSURE METRIC ----------
def pressure_score(home, away):
    h_att,a_att = home['attacks'], away['attacks']
    h_d,a_d = home['danger'], away['danger']
    if (h_att + a_att)<ATTACKS_MIN: return 0.0,0.0
    score_home = 0.35*min(1.0,max(0.0,(h_att-a_att)/max(1,ATTACKS_DIFF))) + \
                 0.55*min(1.0,max(0.0,(h_d-a_d)/max(1,DANGER_DIFF))) + \
                 0.10*min(1.0,(h_att+h_d)/20.0)
    score_away = 0.35*min(1.0,max(0.0,(a_att-h_att)/max(1,ATTACKS_DIFF))) + \
                 0.55*min(1.0,max(0.0,(a_d-h_d)/max(1,DANGER_DIFF))) + \
                 0.10*min(1.0,(a_att+a_d)/20.0)
    return score_home, score_away

# ---------- PREDICTION ----------
def predict_corners_and_line_metrics(current_total, lam_remaining, candidate_line):
    is_fractional = isinstance(candidate_line,float) and (candidate_line%1)!=0
    if is_fractional:
        required = int(math.floor(candidate_line)+1)
        p_win = poisson_tail_ge(required-current_total,lam_remaining)
        p_push = 0.0
        p_lose = 1.0-p_win
    else:
        L = int(candidate_line)
        required = L+1
        p_win = poisson_tail_ge(required-current_total,lam_remaining)
        k_eq = L-current_total
        p_push = poisson_pmf(k_eq,lam_remaining) if k_eq>=0 else 0.0
        p_lose = 1.0-p_win-p_push
    return {'line':candidate_line,'p_win':max(0.0,min(1.0,p_win)),'p_push':max(0.0,min(1.0,p_push)),'p_lose':max(0.0,min(1.0,p_lose))}

def evaluate_candidate_lines(current_total, lam, lines_to_check=None):
    lines_to_check = lines_to_check or [3.5,4.0,4.5,5.0,5.5]
    results = [predict_corners_and_line_metrics(current_total,lam,L) for L in lines_to_check]
    results.sort(key=lambda x:x['p_win'],reverse=True)
    return results

# ---------- MESSAGE & TELEGRAM ----------
def build_vip_message(fixture, window_key, metrics, best_lines):
    teams = fixture['teams']
    home = teams['home']['name']; away = teams['away']['name']
    league = fixture['league'].get('name')
    minute = metrics['minute']
    score = f"{fixture.get('goals',{}).get('home','-')} x {fixture.get('goals',{}).get('away','-')}"
    lines_txt = [f"Linha {ln['line']} → Win {ln['p_win']*100:.0f}% | Push {ln['p_push']*100:.0f}%" for ln in best_lines[:3]]
    pressure_note = 'Pressão detectada' if metrics.get('pressure') else 'Pressão fraca'
    stadium_small = '✅' if metrics.get('small_stadium') else '❌'
    txt = [
        f"📣 <b>SINAL VIP PLUS {window_key}</b> 📣",
        f"🏟 {home} x {away}   |   🏆 {league}",
        f"⏱ Minuto: {minute}   |   ⚽ Placar: {score}",
        f"⛳ Cantos já: {metrics.get('total_corners')} (H:{metrics.get('home_corners')} - A:{metrics.get('away_corners')})",
        f"⚡ Ataques: H:{metrics.get('home_attacks')} A:{metrics.get('away_attacks')}",
        f"🔥 Ataques perigosos: H:{metrics.get('home_danger')} A:{metrics.get('away_danger')}",
        f"🏟 Estádio pequeno: {stadium_small}   |   {pressure_note}",
        "\n<b>Top lines sugeridas (probabilidade de ganhar / prob de reembolso):</b>",
    ]
    txt.extend(lines_txt)
    txt.append("\n<b>Observações:</b> Modelo Poisson + pressão ofensiva. Ajuste odds na Bet365 antes de entrar.")
    txt.append(f"🔗 Bet365: https://www.bet365.com/#/AX/K^{home.replace(' ','')}/")
    return "\n".join(txt)

def send_telegram_message(text):
    if not TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning('TOKEN ou TELEGRAM_CHAT_ID não definido.')
        return
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode":"HTML"}
    try:
        r = requests.post(url,json=payload,timeout=10)
        if r.status_code!=200: logger.warning('Erro ao enviar Telegram: %s %s', r.status_code,r.text)
    except Exception as e:
        logger.exception('Erro ao enviar Telegram: %s', e)

# ---------- MAIN LOOP ----------
def main_loop():
    while True:
        fixtures = get_live_fixtures()
        if not fixtures:
            logger.info('Nenhuma partida ao vivo detectada.')
        for fixture in fixtures:
            fixture_id = fixture['fixture']['id'] if 'fixture' in fixture else fixture.get('id')
            stats = get_fixture_statistics(fixture_id)
            home,away = extract_basic_stats(fixture, stats)
            score_home, score_away = pressure_score(home, away)
            total_corners = home['corners'] + away['corners']
            metrics = {
                'minute': fixture.get('fixture',{}).get('status',{}).get('elapsed',0),
                'home_corners': home['corners'],
                'away_corners': away['corners'],
                'home_attacks': home['attacks'],
                'away_attacks': away['attacks'],
                'home_danger': home['danger'],
                'away_danger': away['danger'],
                'pressure': score_home>MIN_PRESSURE_SCORE or score_away>MIN_PRESSURE_SCORE,
                'small_stadium': fixture.get('fixture',{}).get('venue',{}).get('name','').lower() in SMALL_STADIUMS,
                'total_corners': total_corners
            }
            # avalia linhas
            best_lines = evaluate_candidate_lines(total_corners, lam=1.5)  # pode ajustar lam dinamicamente
            window_key = 'HT' if HT_WINDOW[0]<=metrics['minute']<=HT_WINDOW[1] else 'FT' if FT_WINDOW[0]<=metrics['minute']<=FT_WINDOW[1] else 'LIVE'
            signal_key = f"{window_key}_{total_corners}"
            if signal_key not in sent_signals[fixture_id]:
                msg = build_vip_message(fixture, window_key, metrics, best_lines)
                send_telegram_message(msg)
                sent_signals[fixture_id].add(signal_key)
                logger.info('Sinal enviado: %s', signal_key)
        time.sleep(25)  # intervalo entre verificações

# ---------- START THREAD ----------
if __name__=="__main__":
    import threading
    t = threading.Thread(target=main_loop, daemon=True)
    t.start()
    app.run(host="0.0.0.0", port=int(os.getenv("PORT",10000)), debug=False)