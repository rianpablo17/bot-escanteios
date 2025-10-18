"""
bot_escanteios_rp_v3.py
Versão otimizada: sinais mais frequentes, confiáveis, e layout completo com Bet365
"""

import os
import time
import math
import requests
import logging
from datetime import datetime
from collections import defaultdict
from threading import Thread
from flask import Flask

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------- CONFIG ----------------------
TOKEN = os.getenv('TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
API_FOOTBALL_KEY = os.getenv('API_FOOTBALL_KEY')

# Janela HT/FT
HT_WINDOW_MIN_START = 33
HT_WINDOW_MIN_END = 40
FT_WINDOW_MIN_START = 83
FT_WINDOW_MIN_END = 90

# Prob thresholds ajustados para mais sinais
PROB_THRESHOLD_HIGH = 0.60
PROB_THRESHOLD_2C = 0.55

# Ligas prioritárias (exemplo: Premier League, La Liga, Bundesliga, etc)
priority_leagues = {
    39: 0.05,   # Premier League
    78: 0.05,   # Bundesliga
    140: 0.04,  # La Liga
    61: 0.04,   # Ligue 1
    135: 0.03,  # Serie A
}

# Lista de estádios pequenos (nome em lower-case)
small_stadiums = [
    'loftus road', 'vitality stadium', 'kenilworth road',
    'turf moor', 'crowd', 'bramall lane', 'ewood park',
]

# Controle de sinais enviados
sent_signals = defaultdict(set)

# API-Football
API_BASE = 'https://v3.football.api-sports.io'
HEADERS = {'x-apisports-key': API_FOOTBALL_KEY}

# ---------------------- HELPERS ----------------------
def send_telegram_message(text, parse_mode='HTML'):
    if not TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning('TOKEN ou TELEGRAM_CHAT_ID não configurado. Mensagem não enviada.')
        return
    url = f'https://api.telegram.org/bot{TOKEN}/sendMessage'
    payload = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': text,
        'parse_mode': parse_mode,
        'disable_web_page_preview': True
    }
    try:
        r = requests.post(url, data=payload, timeout=10)
        if r.status_code != 200:
            logger.warning('Erro ao enviar telegram: %s %s', r.status_code, r.text)
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


def get_standings(league_id, season, team_id):
    try:
        r = requests.get(f'{API_BASE}/standings?league={league_id}&season={season}', headers=HEADERS, timeout=10)
        if r.status_code == 200:
            resp = r.json().get('response', [])
            for entry in resp:
                for team in entry.get('league', {}).get('standings', [[]])[0]:
                    if team['team']['id'] == team_id:
                        return team
    except Exception as e:
        logger.debug('Erro ao buscar standings: %s', e)
    return None


def is_small_stadium(venue_name):
    if not venue_name:
        return False
    name = venue_name.lower()
    for s in small_stadiums:
        if s in name:
            return True
    return False


def poisson_prob_ge(k, lam):
    if lam < 0:
        lam = 0
    prob_lt_k = 0.0
    for i in range(0, k):
        prob_lt_k += math.exp(-lam) * (lam ** i) / math.factorial(i)
    return max(0.0, 1.0 - prob_lt_k)


def estimate_probability_of_corners(window_minutes_remaining, current_corners, minute, league_avg_corners_per_min=None):
    if minute <= 0:
        rate = 0.06
    else:
        rate = current_corners / minute
    if league_avg_corners_per_min:
        rate = (rate + league_avg_corners_per_min) / 2
    lam = rate * window_minutes_remaining
    p_ge_1 = poisson_prob_ge(1, lam)
    p_ge_2 = poisson_prob_ge(2, lam)
    return lam, p_ge_1, p_ge_2


def compute_match_score(fixture):
    fixture_id = fixture['fixture']['id']
    league = fixture['league']
    teams = fixture['teams']
    venue = fixture['fixture'].get('venue', {})
    event_minute = fixture['fixture'].get('status', {}).get('elapsed') or 0

    scores = fixture['goals']
    stats = get_fixture_statistics(fixture_id)
    home_corners = 0
    away_corners = 0
    for team_stats in stats:
        team = team_stats.get('team', {})
        if team_stats.get('statistics'):
            for s in team_stats['statistics']:
                if s.get('type', '').lower() in ('corners', 'cantos', 'corner kicks'):
                    val = s.get('value', 0)
                    if team.get('id') == teams['home']['id']:
                        home_corners = val
                    else:
                        away_corners = val
    total_corners = home_corners + away_corners
    venue_name = venue.get('name') if venue else None
    small = is_small_stadium(venue_name)
    league_weight = priority_leagues.get(league.get('id'), 0.0)

    results = {}
    if HT_WINDOW_MIN_START <= event_minute <= HT_WINDOW_MIN_END:
        minutes_remaining = HT_WINDOW_MIN_END - event_minute
        lam, p_ge_1, p_ge_2 = estimate_probability_of_corners(minutes_remaining, total_corners, event_minute)
        bonus = league_weight + (0.15 if small else 0)
        p_ge_1 = min(1.0, p_ge_1 + bonus)
        p_ge_2 = min(1.0, p_ge_2 + bonus)
        results['HT'] = {
            'minute': event_minute,
            'home_corners': home_corners,
            'away_corners': away_corners,
            'total_corners': total_corners,
            'lam': lam,
            'p_ge_1': p_ge_1,
            'p_ge_2': p_ge_2,
            'small_stadium': small,
            'league_weight': league_weight
        }

    if FT_WINDOW_MIN_START <= event_minute <= FT_WINDOW_MIN_END:
        minutes_remaining = FT_WINDOW_MIN_END - event_minute
        lam, p_ge_1, p_ge_2 = estimate_probability_of_corners(minutes_remaining, total_corners, event_minute)
        bonus = league_weight + (0.15 if small else 0)
        p_ge_1 = min(1.0, p_ge_1 + bonus)
        p_ge_2 = min(1.0, p_ge_2 + bonus)
        results['FT'] = {
            'minute': event_minute,
            'home_corners': home_corners,
            'away_corners': away_corners,
            'total_corners': total_corners,
            'lam': lam,
            'p_ge_1': p_ge_1,
            'p_ge_2': p_ge_2,
            'small_stadium': small,
            'league_weight': league_weight
        }

    return results


def build_signal_text(fixture, window_key, metrics):
    league = fixture['league']
    teams = fixture['teams']
    fixture_info = fixture['fixture']
    minute = metrics.get('minute', 0)
    home = teams['home']['name']
    away = teams['away']['name']

    season = league.get('season')
    home_pos = get_standings(league.get('id'), season, teams['home']['id'])
    away_pos = get_standings(league.get('id'), season, teams['away']['id'])

    position_text = ''
    if home_pos:
        position_text += f"{home} (#{home_pos.get('rank')})"
    else:
        position_text += f"{home}"
    position_text += ' x '
    if away_pos:
        position_text += f"{away} (#{away_pos.get('rank')})"
    else:
        position_text += f"{away}"

    comp = league.get('name')
    current_score = f"{fixture.get('goals', {}).get('home', '-') } x {fixture.get('goals', {}).get('away', '-') }"

    txt = []
    txt.append(f"🚨 <b>SINAL {window_key} - ESCANTEIOS</b> 🚨")
    txt.append(f"<b>Partida:</b> {position_text}")
    txt.append(f"<b>Competição:</b> {comp}")
    txt.append(f"<b>Minuto:</b> {minute}   |   <b>Placar:</b> {current_score}")
    txt.append(f"<b>Cantos já saídos:</b> {metrics.get('total_corners')} (H: {metrics.get('home_corners')} - A: {metrics.get('away_corners')})")
    txt.append(f"<b>Probabilidade ≥1 canto:</b> {metrics.get('p_ge_1')*100:.0f}%")
    txt.append(f"<b>Probabilidade ≥2 cantos:</b> {metrics.get('p_ge_2')*100:.0f}%")
    txt.append(f"<b>Estádio pequeno:</b> {'✅' if metrics.get('small_stadium') else '❌'}")
    txt.append(f"<b>Observações:</b> janela {window_key} | estratégia: 1-2 escanteios asiáticos")
    txt.append(f"<b>Link Bet365:</b> https://www.bet365.com/#/AC/B1/C1/D13/E{{league_id}}/F{{fixture_id}}")  # Exemplo dinâmico
    txt.append('\n<b>⚠️ Nota:</b> Probabilidades estimadas via heurística — ajuste thresholds conforme quiser.')
    return '\n'.join(txt)


def process_fixtures_and_send():
    fixtures = get_live_fixtures()
    if not fixtures:
        logger.info('Sem partidas ao vivo.')
        return

    for fixture in fixtures:
        fixture_id = fixture['fixture']['id']

        # ✅ Corrige delay da API adicionando 1 minuto
        event_minute = fixture['fixture'].get('status', {}).get('elapsed', 0) + 1

        metrics_per_window = compute_match_score(fixture)
        for window_key, metrics in metrics_per_window.items():
            # Ajusta minuto com correção
            metrics['minute'] = event_minute

            send_for_1 = metrics['p_ge_1'] >= PROB_THRESHOLD_HIGH
            send_for_2 = metrics['p_ge_2'] >= PROB_THRESHOLD_2C
            already_sent_key = f"{window_key}:{'2' if send_for_2 else '1'}"

            if (send_for_2 or send_for_1) and already_sent_key not in sent_signals[fixture_id]:
                text = build_signal_text(fixture, window_key, metrics)
                send_telegram_message(text)
                sent_signals[fixture_id].add(already_sent_key)
                logger.info(
                    'Sinal enviado para fixture %s window %s (p1=%.2f p2=%.2f)',
                    fixture_id, window_key, metrics['p_ge_1'], metrics['p_ge_2']
                )

# ✅ Reduz tempo entre checagens para 5 segundos
def start_loop():
    try:
        while True:
            try:
                process_fixtures_and_send()
            except Exception as e:
                logger.exception('Erro no loop de processamento: %s', e)
            time.sleep(5)  # polling mais rápido, reduz delay
    except KeyboardInterrupt:
        logger.info('Interrompido pelo usuário')


def start_loop():
    try:
        while True:
            try:
                process_fixtures_and_send()
            except Exception as e:
                logger.exception('Erro no loop de processamento: %s', e)
            time.sleep(10)  # polling leve para pegar partidas HT/FT
    except KeyboardInterrupt:
        logger.info('Interrompido pelo usuário')


# ---------------------- FLASK WEB ----------------------
app = Flask('bot_health')

@app.route("/healthz")
def health():
    return "ok", 200

@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    return "ok", 200  # evita 404 do Telegram

if __name__ == '__main__':
    Thread(target=start_loop, daemon=True).start()
    port = int(os.getenv('PORT', '10000'))
    logger.info('🌐 Webhook ativo: https://%s/%s', os.getenv('PRIMARY_URL', 'bot-escanteios17.onrender.com'), TOKEN)
    app.run(host='0.0.0.0', port=port)