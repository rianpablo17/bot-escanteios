"""
bot_escanteios_rp_v3_final.py
Versão final adaptada: sinais inteligentes HT/FT baseados em pressão ofensiva
- 1 sinal por tempo
- Apenas link Bet365
- Janela estratégica HT 35–40 / FT 80–90
- Heurística de pressão ofensiva priorizada sobre número de escanteios
"""

import os
import time
import math
import requests
import logging
from collections import defaultdict
from threading import Thread
from flask import Flask

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------- CONFIG ----------------------
TOKEN = os.getenv('TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
API_FOOTBALL_KEY = os.getenv('API_FOOTBALL_KEY')

HT_WINDOW_MIN_START = 35
HT_WINDOW_MIN_END = 40
FT_WINDOW_MIN_START = 80
FT_WINDOW_MIN_END = 90

PROB_THRESHOLD_HIGH = 0.60
PROB_THRESHOLD_2C = 0.55

PRESSURE_ATTACKS_DIFF = 5
PRESSURE_ATTACKS_ABS = 8
PRESSURE_DANGEROUS_ABS = 5
PRESSURE_DANGEROUS_DIFF = 3

priority_leagues = {39:0.05, 78:0.05, 140:0.04, 61:0.04, 135:0.03}
small_stadiums = ['loftus road','vitality stadium','kenilworth road','turf moor','crowd','bramall lane','ewood park']
sent_signals = defaultdict(set)
API_BASE = 'https://v3.football.api-sports.io'
HEADERS = {'x-apisports-key': API_FOOTBALL_KEY}

# ---------------------- HELPERS ----------------------
def send_telegram_message(text):
    if not TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning('TOKEN ou TELEGRAM_CHAT_ID não configurado.')
        return
    url = f'https://api.telegram.org/bot{TOKEN}/sendMessage'
    payload = {'chat_id': TELEGRAM_CHAT_ID,'text': text,'parse_mode':'HTML','disable_web_page_preview':True}
    try:
        r = requests.post(url,data=payload,timeout=10)
        if r.status_code != 200:
            logger.warning('Erro Telegram: %s %s', r.status_code, r.text)
    except Exception as e:
        logger.exception('Falha ao enviar telegram: %s', e)


def get_live_fixtures():
    try:
        r = requests.get(f'{API_BASE}/fixtures?live=all', headers=HEADERS, timeout=10)
        if r.status_code == 200:
            return r.json().get('response', [])
    except Exception as e:
        logger.exception('Erro ao buscar fixtures: %s', e)
    return []


def get_fixture_statistics(fixture_id):
    try:
        r = requests.get(f'{API_BASE}/fixtures/statistics?fixture={fixture_id}', headers=HEADERS, timeout=10)
        if r.status_code == 200:
            return r.json().get('response', [])
    except Exception as e:
        logger.exception('Erro ao buscar statistics: %s', e)
    return []


def is_small_stadium(name):
    if not name: return False
    return any(s in name.lower() for s in small_stadiums)


def poisson_prob_ge(k, lam):
    prob_lt_k = sum(math.exp(-lam)(lam*i)/math.factorial(i) for i in range(k))
    return max(0.0, 1.0 - prob_lt_k)


def estimate_probability_of_corners(window_min, current_corners, minute, league_avg=None):
    rate = (current_corners / minute) if minute>0 else 0.06
    if league_avg: rate = (rate + league_avg)/2
    lam = rate*window_min
    return lam, poisson_prob_ge(1, lam), poisson_prob_ge(2, lam)


def _extract_stats(stats_resp, teams):
    home_id = teams['home']['id']
    away_id = teams['away']['id']
    home = {'corners':0,'attacks':0,'dangerous_attacks':0}
    away = {'corners':0,'attacks':0,'dangerous_attacks':0}
    for entry in stats_resp:
        team_id = entry.get('team',{}).get('id')
        stats_list = entry.get('statistics') or []
        target = home if team_id==home_id else away
        for s in stats_list:
            t = s.get('type','').lower()
            val = s.get('value') or 0
            if 'corner' in t: target['corners']=int(val)
            elif 'attack' in t: target['attacks']=int(val)
            elif 'dangerous' in t or 'on target' in t: target['dangerous_attacks']=int(val)
    return home, away


def detect_pressure(h,a):
    cond_abs = (h['attacks']>=PRESSURE_ATTACKS_ABS or h['dangerous_attacks']>=PRESSURE_DANGEROUS_ABS)
    cond_diff = ((h['attacks']-a['attacks'])>=PRESSURE_ATTACKS_DIFF or (h['dangerous_attacks']-a['dangerous_attacks'])>=PRESSURE_DANGEROUS_DIFF)
    if cond_abs and cond_diff: return True
    if h['dangerous_attacks']>=PRESSURE_DANGEROUS_ABS and (h['dangerous_attacks']-a['dangerous_attacks'])>=2: return True
    return False


def compute_match_score(fixture):
    f_id = fixture['fixture']['id']
    league = fixture['league']
    teams = fixture['teams']
    venue_name = fixture['fixture'].get('venue',{}).get('name')
    minute = fixture['fixture'].get('status',{}).get('elapsed') or 0

    stats_resp = get_fixture_statistics(f_id)
    home_stats, away_stats = _extract_stats(stats_resp, teams)
    home_corners = home_stats['corners']; away_corners = away_stats['corners']; total_corners = home_corners+away_corners

    small = is_small_stadium(venue_name)
    league_weight = priority_leagues.get(league['id'],0.0)

    results = {}

    for window_key,(start,end) in {'HT':(HT_WINDOW_MIN_START,HT_WINDOW_MIN_END),'FT':(FT_WINDOW_MIN_START,FT_WINDOW_MIN_END)}.items():
        if start <= minute <= end:
            lam,p_ge1,p_ge2 = estimate_probability_of_corners(end-minute,total_corners,minute)
            bonus = league_weight + (0.15 if small else 0)
            p_ge1 = min(1.0,p_ge1+bonus)
            p_ge2 = min(1.0,p_ge2+bonus)
            home_pressure = detect_pressure(home_stats,away_stats)
            away_pressure = detect_pressure(away_stats,home_stats)
            pressure = home_pressure or away_pressure
            pressure_side = 'both' if home_pressure and away_pressure else ('home' if home_pressure else 'away' if away_pressure else 'none')

            results[window_key] = {'minute':minute,'home_corners':home_corners,'away_corners':away_corners,'total_corners':total_corners,
                                   'p_ge_1':p_ge1,'p_ge_2':p_ge2,'small_stadium':small,'pressure':pressure,'pressure_side':pressure_side,
                                   'home_stats':home_stats,'away_stats':away_stats}
    return results


def build_signal_text(fixture, window_key, metrics):
    teams = fixture['teams']
    minute = metrics['minute']
    home, away = teams['home']['name'], teams['away']['name']
    score = f"{fixture.get('goals',{}).get('home','-')} x {fixture.get('goals',{}).get('away','-')}"
    hc,ac = metrics['home_corners'], metrics['away_corners']
    ha,aa = metrics['home_stats']['attacks'], metrics['away_stats']['attacks']
    hd,ad = metrics['home_stats']['dangerous_attacks'], metrics['away_stats']['dangerous_attacks']

    txt = []
    txt.append(f"🚨 <b>SINAL {window_key} - ESCANTEIOS</b> 🚨")
    txt.append(f"<b>Partida:</b> {home} x {away}")
    txt.append(f"<b>Minuto:</b> {minute} | <b>Placar:</b> {score}")
    txt.append(f"<b>Cantos já saídos:</b> {hc+ac} (H:{hc} - A:{ac})")
    txt.append(f"<b>Ataques (H x A):</b> {ha} x {aa}")
    txt.append(f"<b>Ataques perigosos (H x A):</b> {hd} x {ad}")
    txt.append(f"<b>Estádio pequeno:</b> {'✅' if metrics['small_stadium'] else '❌'}")
    rec = f"+4/+4.5 asiáticos HT" if window_key=='HT' else f"+9/+9.5 asiáticos FT"
    if metrics['pressure']: rec += " (pressão detectada