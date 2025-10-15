"""
bot_escanteios_rp_v2.py
Versão atualizada do seu bot de escanteios (Rian) — envia sinais HT/FT baseados em probabilidade de 1 ou 2 escanteios
Principais recursos implementados:
- Não depende do time da casa estar perdendo
- Envia sinais HT (janela 35-45) e FT (janela 80-90) quando a probabilidade de sair >=1 ou >=2 escanteios asiáticos for alta
- Dá peso a jogos em campos pequenos e a ligas com histórico alto de escanteios
- Analisa partidas globalmente, mas prioriza ligas com alta média de cantos
- Mensagem de sinal explicativa (placar, minuto, tabela/posição quando disponível, competição, cantos já saídos, probabilidade etc.)
- Proteção para não enviar sinal duplicado por jogo/janela

DEPENDÊNCIAS:
- requests
- python-telegram-bot==20.x (ou usa chamadas diretas à API HTTP do Telegram)
- python-dateutil (opcional)

CONFIGURAÇÃO (variáveis de ambiente):
- TELEGRAM_TOKEN
- TELEGRAM_CHAT_ID (ou lista / lógica para envio)
- API_FOOTBALL_KEY

OBS: Ajuste os thresholds e listas (small_stadiums, priority_leagues) conforme sua experiência.
"""

import os
import time
import math
import requests
import logging
from datetime import datetime
from collections import defaultdict

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------- CONFIG ----------------------
TELEGRAM_TOKEN = os.getenv('TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')  # pode ser um chat id ou canal
API_FOOTBALL_KEY = os.getenv('API_FOOTBALL_KEY')

# Se não usar TELEGRAM_CHAT_ID global, pode implementar lógica para cada grupo
POLL_INTERVAL = int(os.getenv('POLL_INTERVAL', '20'))  # em segundos
HT_WINDOW_MIN_START = 35
HT_WINDOW_MIN_END = 45
FT_WINDOW_MIN_START = 80
FT_WINDOW_MIN_END = 90

# Prob thresholds (ajuste conforme preferir)
PROB_THRESHOLD_HIGH = 0.70  # prob de >=1 ou >=2 (dependendo da estratégia) para enviar
PROB_THRESHOLD_2C = 0.65  # prob de >=2

# Listas de exemplo — adapte com sua experiência local
priority_leagues = {
    # league_id: weight (additive)
    # Exemplo genérico: coloque os IDs das ligas que você quer priorizar
}

# Lista manual de estádios conhecidos como 'pequenos' (nomes em lower-case para comparação)
small_stadiums = [
    'loftus road', 'vitality stadium', 'kenilworth road',
    'turf moor', 'crowd', 'bramall lane', 'ewood park',
    # adicione mais nomes que você conhece
]

# controle para não enviar duplicado: sent_signals[fixture_id] = set(['HT','FT-2','FT-1'])
sent_signals = defaultdict(set)

# API-Football base
API_BASE = 'https://v3.football.api-sports.io'
HEADERS = {'x-apisports-key': API_FOOTBALL_KEY}

# ---------------------- HELPERS ----------------------

def send_telegram_message(text, parse_mode='HTML'):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning('TELEGRAM_TOKEN ou TELEGRAM_CHAT_ID não configurado. Mensagem não enviada.')
        return
    url = f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage'
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
    # Pega fixtures ao vivo
    try:
        r = requests.get(f'{API_BASE}/fixtures?live=all', headers=HEADERS, timeout=10)
        if r.status_code == 200:
            return r.json().get('response', [])
        else:
            logger.warning('Erro API-Football fixtures: %s %s', r.status_code, r.text)
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
    # tenta pegar posição na tabela para message
    try:
        r = requests.get(f'{API_BASE}/standings?league={league_id}&season={season}', headers=HEADERS, timeout=10)
        if r.status_code == 200:
            resp = r.json().get('response', [])
            for entry in resp:
                for team in entry.get('league', {}).get('standings', [[]])[0]:
                    if team['team']['id'] == team_id:
                        return team  # contém position, points etc.
    except Exception as e:
        logger.debug('Erro ao buscar standings: %s', e)
    return None


def get_league_avg_corners(league_id, season):
    # tentativa: usar endpoint 'teams/statistics' ou similar não é direto;
    # se não encontrar, volta None e usamos heurística baseada no jogo atual
    return None


def is_small_stadium(venue_name):
    if not venue_name:
        return False
    name = venue_name.lower()
    for s in small_stadiums:
        if s in name:
            return True
    return False


# ---------------------- PROBABILITY / MODEL ----------------------

def poisson_prob_ge(k, lam):
    # probabilidade Pr(X >= k) para Poisson(lambda)
    # P(X < k) = sum_{i=0}^{k-1} e^{-lam} lam^i / i!
    # então P(X >= k) = 1 - P(X < k)
    if lam < 0:
        lam = 0
    prob_lt_k = 0.0
    for i in range(0, k):
        prob_lt_k += math.exp(-lam) * (lam ** i) / math.factorial(i)
    return max(0.0, 1.0 - prob_lt_k)


def estimate_probability_of_corners(window_minutes_remaining, current_corners, minute, league_avg_corners_per_min=None):
    # Estimativa simples: taxa atual (corners/min) * minutos_restantes -> lambda
    # Se minute == 0, evitamos divisão por zero
    if minute <= 0:
        rate = 0.06  # suposição conservadora: 0.06 corners/min (~2.7 corners em 45')
    else:
        rate = current_corners / minute
    if league_avg_corners_per_min:
        # média entre taxa atual e média da liga
        rate = (rate + league_avg_corners_per_min) / 2
    lam = rate * window_minutes_remaining
    # prob >=1 e >=2
    p_ge_1 = poisson_prob_ge(1, lam)
    p_ge_2 = poisson_prob_ge(2, lam)
    return lam, p_ge_1, p_ge_2


def compute_match_score(fixture):
    # Retorna um dict com todas as métricas e probabilidades calculadas
    # fixture: item retornado pelo endpoint /fixtures (objeto)

    fixture_id = fixture['fixture']['id']
    league = fixture['league']
    teams = fixture['teams']
    venue = fixture['fixture'].get('venue', {})
    event_minute = fixture['fixture'].get('status', {}).get('elapsed') or 0
    scores = fixture['goals']

    # pegar cantos via statistics endpoint
    stats = get_fixture_statistics(fixture_id)
    home_corners = 0
    away_corners = 0
    for team_stats in stats:
        team = team_stats.get('team', {})
        if team_stats.get('statistics'):
            for s in team_stats['statistics']:
                if s.get('type', '').lower() in ('corners', 'cantos', 'corner kicks'):
                    # value geralmente está em 'value' ou 'value' dentro
                    # API-Football retorna 'value' e 'type'
                    val = s.get('value', 0)
                    if team.get('id') == teams['home']['id']:
                        home_corners = val
                    else:
                        away_corners = val
    total_corners = home_corners + away_corners

    # detecta se estádio pequeno
    venue_name = venue.get('name') if venue else None
    small = is_small_stadium(venue_name)

    # league weight (se tiver list)
    league_weight = 0.0
    lid = league.get('id')
    if lid in priority_leagues:
        league_weight = priority_leagues[lid]

    # heurística para janelas
    results = {}

    # Janela HT
    if HT_WINDOW_MIN_START <= (event_minute or 0) <= HT_WINDOW_MIN_END:
        minutes_remaining = HT_WINDOW_MIN_END - (event_minute or 0)
        lam, p_ge_1, p_ge_2 = estimate_probability_of_corners(minutes_remaining, total_corners, event_minute)
        # aplicar pesos
        bonus = 0.0
        if small:
            bonus += 0.15
        bonus += league_weight
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

    # Janela FT (final do jogo)
    if FT_WINDOW_MIN_START <= (event_minute or 0) <= FT_WINDOW_MIN_END:
        minutes_remaining = FT_WINDOW_MIN_END - (event_minute or 0)
        lam, p_ge_1, p_ge_2 = estimate_probability_of_corners(minutes_remaining, total_corners, event_minute)
        bonus = 0.0
        if small:
            bonus += 0.15
        bonus += league_weight
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


# ---------------------- MAIN LOOP ----------------------

def build_signal_text(fixture, window_key, metrics):
    league = fixture['league']
    teams = fixture['teams']
    fixture_info = fixture['fixture']
    score = fixture_info.get('status', {}).get('long')
    minute = metrics.get('minute', 0)
    home = teams['home']['name']
    away = teams['away']['name']

    # tentativa de buscar posições na tabela
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
    txt.append(f"<b>Observações:</b> janela { 'HT' if window_key=='HT' else 'FT'} | estratégia: 1-2 escanteios asiáticos")

    txt.append('\n<b>⚠️ Nota:</b> Probabilidades estimadas via heurística — ajuste thresholds conforme quiser.')

    return '\n'.join(txt)


def process_fixtures_and_send():
    fixtures = get_live_fixtures()
    if not fixtures:
        logger.debug('Nenhuma partida ao vivo no momento.')
        return

    for fixture in fixtures:
        fixture_id = fixture['fixture']['id']
        logger.debug('Analisando fixture %s', fixture_id)
        metrics_per_window = compute_match_score(fixture)
        for window_key, metrics in metrics_per_window.items():
            # decide se envia
            # criterio: se prob >= threshold
            send_for_1 = metrics['p_ge_1'] >= PROB_THRESHOLD_HIGH
            send_for_2 = metrics['p_ge_2'] >= PROB_THRESHOLD_2C
            already_sent_key = f"{window_key}:{'2' if send_for_2 else '1'}"
            if (send_for_2 or send_for_1) and already_sent_key not in sent_signals[fixture_id]:
                # build message
                text = build_signal_text(fixture, window_key, metrics)
                send_telegram_message(text)
                sent_signals[fixture_id].add(already_sent_key)
                logger.info('Sinal enviado para fixture %s window %s (p1=%.2f p2=%.2f)', fixture_id, window_key, metrics['p_ge_1'], metrics['p_ge_2'])


from threading import Thread
from flask import Flask
import os

# Loop do bot
def start_loop():
    try:
        while True:
            try:
                process_fixtures_and_send()
            except Exception as e:
                logger.exception('Erro no loop de processamento: %s', e)
            time.sleep(POLL_INTERVAL)
    except KeyboardInterrupt:
        logger.info('Interrompido pelo usuário')

# Webserver mínimo para satisfazer o Render
app = Flask('bot_health')

@app.route("/healthz")
def health():
    return "ok", 200

if __name__ == '__main__':
    # inicia loop do bot em segundo plano
    Thread(target=start_loop, daemon=True).start()
    
    # inicia webserver na porta do Render
    port = int(os.getenv('PORT', '10000'))
    logger.info('Iniciando webserver de health na porta %s', port)
    app.run(host='0.0.0.0', port=port)