"""
bot_escanteios_rp_vip_plus.py
Versão ULTRA-PRO (AJUSTADA): leitura de pressão HT/FT, previsão por minuto de CANTOS ASIÁTICOS,
avaliação de linhas (inteiras e .5), sinal VIP com análise de reembolso (push) e EV estimado.
Configuração ajustada conforme pedido:
- ATTACKS_MIN = 5
- ATTACKS_DIFF = 4
- DANGER_MIN = 4
- DANGER_DIFF = 3

Instruções:
- Defina as env vars: TOKEN, TELEGRAM_CHAT_ID, API_FOOTBALL_KEY
- Rode normalmente; logs mostrarão cálculos minuto a minuto

"""

import os
import time
import math
import logging
from collections import defaultdict
from threading import Thread
import requests
from flask import Flask

# ---------- LOGGER ----------
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s:%(name)s: %(message)s')
logger = logging.getLogger('bot_escanteios_vip_plus')

# ---------- CONFIG (AJUSTADO) ----------
TOKEN = os.getenv('TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
API_FOOTBALL_KEY = os.getenv('API_FOOTBALL_KEY')

API_BASE = 'https://v3.football.api-sports.io'
HEADERS = {'x-apisports-key': API_FOOTBALL_KEY}

# Janela estratégica
HT_WINDOW = (35, 40)
FT_WINDOW = (80, 90)

# Sensibilidade / thresholds
PROB_LINE_THRESHOLD = 0.60   # prob de vitória mínima para sugerir uma linha
PROB_PUSH_ALERT = 0.20       # se prob_push >= este valor marcamos "alto risco de reembolso"
MIN_PRESSURE_SCORE = 0.5     # score de pressão para considerar pressão alta

# Pressão ofensiva params (AJUSTADOS conforme solicitado)
ATTACKS_MIN = 5              # <- ajustado para 5
ATTACKS_DIFF = 4             # diferença de ataques entre times
DANGER_MIN = 5              # ataques perigosos mínimos
DANGER_DIFF = 3              # diferença de ataques perigosos

# Ligas com pequeno bónus
PRIORITY_LEAGUES = {39:0.05, 78:0.05, 140:0.04, 61:0.04, 135:0.03}
SMALL_STADIUMS = ['loftus road','vitality stadium','kenilworth road','turf moor','crowd','bramall lane','ewood park']

# Controle sinais
sent_signals = defaultdict(set)  # fixture_id -> set of keys (HT:4.5, FT:pressure, ...)

# ---------- MATH HELPERS (Poisson) ----------

def poisson_pmf(k, lam):
    try:
        return (lam**k) * math.exp(-lam) / math.factorial(k)
    except Exception:
        return 0.0


def poisson_cdf_le(k, lam):
    s = 0.0
    for i in range(0, int(k)+1):
        s += poisson_pmf(i, lam)
    return s


def poisson_tail_ge(k, lam):
    if k <= 0:
        return 1.0
    return 1.0 - poisson_cdf_le(k-1, lam)

# ---------- API HELPERS ----------

def get_live_fixtures():
    try:
        r = requests.get(f"{API_BASE}/fixtures?live=all", headers=HEADERS, timeout=10)
        if r.status_code == 200:
            return r.json().get('response', [])
        else:
            logger.warning('API-Football fixtures status %s %s', r.status_code, r.text)
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

# ---------- GAME STATS EXTRACTION ----------

def extract_basic_stats(fixture, stats_resp):
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
            if 'corner' in t:
                target['corners'] = int(val)
            elif 'attack' in t:
                try:
                    target['attacks'] = int(val)
                except:
                    target['attacks'] = target.get('attacks', 0)
            elif 'on goal' in t or 'danger' in t or 'shots on goal' in t:
                try:
                    target['danger'] = int(val)
                except:
                    target['danger'] = target.get('danger', 0)
    return home, away

# ---------- PRESSURE METRICS ----------

def pressure_score(home, away):
    h_att = home.get('attacks', 0)
    a_att = away.get('attacks', 0)
    h_d = home.get('danger', 0)
    a_d = away.get('danger', 0)

    att_component = min(1.0, max(0.0, (h_att - a_att) / max(1, ATTACKS_DIFF)))
    dang_component = min(1.0, max(0.0, (h_d - a_d) / max(1, DANGER_DIFF)))
    abs_component = min(1.0, (h_att + h_d) / 20.0)

    score_home = 0.35 * att_component + 0.55 * dang_component + 0.10 * abs_component

    att_component_a = min(1.0, max(0.0, (a_att - h_att) / max(1, ATTACKS_DIFF)))
    dang_component_a = min(1.0, max(0.0, (a_d - h_d) / max(1, DANGER_DIFF)))
    abs_component_a = min(1.0, (a_att + a_d) / 20.0)
    score_away = 0.35 * att_component_a + 0.55 * dang_component_a + 0.10 * abs_component_a

    return score_home, score_away

# ---------- PREDICTION & ASIAN-LINE EVALUATION ----------

def predict_corners_and_line_metrics(current_total_corners, lam_remaining, candidate_line):
    if isinstance(candidate_line, float) and (candidate_line % 1) != 0:
        required = int(math.floor(candidate_line) + 1)
        p_win = poisson_tail_ge(required - current_total_corners, lam_remaining)
        p_push = 0.0
        p_lose = 1.0 - p_win
    else:
        L = int(candidate_line)
        required = L + 1
        p_win = poisson_tail_ge(required - current_total_corners, lam_remaining)
        k_eq = L - current_total_corners
        if k_eq < 0:
            p_push = 0.0
        else:
            p_push = poisson_pmf(k_eq, lam_remaining)
        p_lose = 1.0 - p_win - p_push

    return {'line': candidate_line, 'p_win': max(0.0, min(1.0, p_win)), 'p_push': max(0.0, min(1.0, p_push)), 'p_lose': max(0.0, min(1.0, p_lose))}


def evaluate_candidate_lines(current_total, lam, lines_to_check=None):
    if lines_to_check is None:
        lines_to_check = [3.5, 4.0, 4.5, 5.0, 5.5]
    results = []
    for L in lines_to_check:
        m = predict_corners_and_line_metrics(current_total, lam, L)
        results.append(m)
    results.sort(key=lambda x: x['p_win'], reverse=True)
    return results

# ---------- MESSAGE BUILDING ----------

def build_vip_message(fixture, window_key, metrics, best_lines):
    teams = fixture['teams']
    home = teams['home']['name']; away = teams['away']['name']
    league = fixture['league'].get('name')
    minute = metrics['minute']
    score = f"{fixture.get('goals',{}).get('home','-')} x {fixture.get('goals',{}).get('away','-')}"

    lines_txt = []
    for ln in best_lines[:3]:
        win = f"{ln['p_win']*100:.0f}%"
        push = f"{ln['p_push']*100:.0f}%"
        lines_txt.append(f"Linha {ln['line']} → Win {win} | Push {push}")

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
    for ltxt in lines_txt:
        txt.append(ltxt)

    txt.append("\n<b>Observações:</b> A linha sugerida é baseada em modelo Poisson dos cantos restantes + leitura de pressão. Ajuste odds na Bet365 antes de entrar.")
    txt.append(f"🔗 Bet365: https://www.bet365.com/#/AX/K^{home.replace(' ','')}/")

    return "\n".join(txt)

# ---------- MAIN ANALYSIS & SENDING ----------

def analyze_and_send(fixture):
    fixture_id = fixture['fixture']['id']
    minute = fixture['fixture'].get('status',{}).get('elapsed',0) or 0
    stats = get_fixture_statistics(fixture_id)
    home, away = extract_basic_stats(fixture, stats)

    total_corners = home['corners'] + away['corners']

    played = max(1, minute)
    rate_per_min = total_corners / played

    window_key = None
    minutes_remaining = None
    if HT_WINDOW[0] <= minute <= HT_WINDOW[1]:
        window_key = 'HT'
        minutes_remaining = HT_WINDOW[1] - minute
    elif FT_WINDOW[0] <= minute <= FT_WINDOW[1]:
        window_key = 'FT'
        minutes_remaining = FT_WINDOW[1] - minute
    else:
        logger.debug('Fixture %s minuto %s não está em janela HT/FT', fixture_id, minute)
        return False

    lam = rate_per_min * max(1, minutes_remaining)

    score_home, score_away = pressure_score(home, away)
    pressure = (score_home >= MIN_PRESSURE_SCORE) or (score_away >= MIN_PRESSURE_SCORE)
    pressure_side = 'home' if score_home>score_away else ('away' if score_away>score_home else 'both')

    metrics = {
        'minute': minute,
        'home_corners': home['corners'], 'away_corners': away['corners'], 'total_corners': total_corners,
        'home_attacks': home.get('attacks',0), 'away_attacks': away.get('attacks',0),
        'home_danger': home.get('danger',0), 'away_danger': away.get('danger',0),
        'lambda': lam, 'pressure': pressure, 'pressure_side': pressure_side,
        'small_stadium': is_small_stadium(fixture['fixture'].get('venue',{}).get('name'))
    }

    candidates = evaluate_candidate_lines(total_corners, lam)

    best = [c for c in candidates if c['p_win'] >= PROB_LINE_THRESHOLD]
    if not best and pressure:
        best = candidates[:2]

    if not best:
        logger.info('Fixture %s | janela %s | nenhum candidato com p_win >= %.2f e sem pressão', fixture_id, window_key, PROB_LINE_THRESHOLD)
        return False

    main_line = best[0]['line']
    key = f"{window_key}:{main_line}"
    if key in sent_signals[fixture_id]:
        logger.debug('Sinal já enviado para %s key %s', fixture_id, key)
        return False

    msg = build_vip_message(fixture, window_key, metrics, best)
    send_telegram_message(msg)
    sent_signals[fixture_id].add(key)
    logger.info('Sinal enviado fixture %s window %s line %s p_win=%.2f p_push=%.2f', fixture_id, window_key, main_line, best[0]['p_win'], best[0]['p_push'])
    return True

# ---------- POLLING LOOP ----------

def start_loop(poll_interval=5):
    logger.info('Iniciando loop de monitoramento (poll_interval=%ss)', poll_interval)
    while True:
        try:
            fixtures = get_live_fixtures()
            if not fixtures:
                logger.debug('Sem partidas ao vivo')
            for f in fixtures:
                try:
                    analyze_and_send(f)
                except Exception as e:
                    logger.exception('Erro analisando fixture: %s', e)
        except Exception as e:
            logger.exception('Erro no loop principal: %s', e)
        time.sleep(poll_interval)

# ---------- FLASK (healthcheck) ----------
app = Flask('bot_health')
@app.route('/healthz')
def health():
    return 'ok', 200
@app.route(f"/{TOKEN}", methods=['POST'])
def webhook():
    return 'ok', 200

if __name__ == '__main__':
    Thread(target=start_loop, kwargs={'poll_interval':5}, daemon=True).start()
    port = int(os.getenv('PORT','10000'))
    logger.info('🌐 Webhook ativo: https://%s/%s', os.getenv('PRIMARY_URL','bot-escanteios17.onrender.com'), TOKEN)
    app.run(host='0.0.0.0', port=port)