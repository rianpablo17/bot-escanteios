#!/usr/bin/env python3
# -- coding: utf-8 --
"""
bot_escanteios_rp_vip_plus_final.py
Versão corrigida e completa — pronto para rodar.

Requisitos:
- Python 3.8+
- pip install requests flask

Environment variables required:
- API_FOOTBALL_KEY  (sua key do api-football)
- TOKEN            (Telegram bot token, ex: 123456:ABC-DEF...)
- TELEGRAM_CHAT_ID (chat id do grupo/usuario)
- WEBHOOK_URL      (opcional; deixei configuração mas o script usa sendMessage direto)

Principais melhorias:
- HEADERS usa os.getenv(...) corretamente
- Logs detalhados (erros de API, status codes)
- Parsing robusto de statistics
- Estimativa de lambda (Poisson) baseada em taxa atual de cantos por minuto
- Evita re-envio via sent_signals
- Função smoke_test() para checagem rápida
- Envio via Telegram com HTML seguro
- Timeouts, tratamento de exceções
"""

import os
import time
import math
import logging
from collections import defaultdict
from typing import Tuple, Dict, Any, List
import requests
from flask import Flask, jsonify

# ---------- CONFIG ----------
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO').upper()
logging.basicConfig(level=LOG_LEVEL, format='%(asctime)s %(levelname)s:%(name)s: %(message)s')
logger = logging.getLogger('bot_escanteios_vip_plus')

# env vars
API_FOOTBALL_KEY = os.getenv('API_FOOTBALL_KEY')
TOKEN = os.getenv('TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
WEBHOOK_URL = os.getenv('WEBHOOK_URL')  # opcional, não usado para sendMessage por padrão

API_BASE = 'https://v3.football.api-sports.io'
HEADERS = {"x-apisports-key": API_FOOTBALL_KEY} if API_FOOTBALL_KEY else {}

# Janela estratégica
HT_WINDOW = (32, 40)   # minutos para HT-signal
FT_WINDOW = (80, 90)   # minutos para FT-signal

# Sensibilidade / thresholds (ajustáveis)
PROB_LINE_THRESHOLD = 0.60   # prob de vitória mínima para sugerir uma linha
PROB_PUSH_ALERT = 0.20       # se prob_push >= este valor marcamos "alto risco de reembolso"
MIN_PRESSURE_SCORE = 0.5     # score de pressão para considerar pressão alta

# Pressão ofensiva params (AJUSTADOS)
ATTACKS_MIN = 5
ATTACKS_DIFF = 4
DANGER_MIN = 5
DANGER_DIFF = 3

# Ligas com pequeno bónus (ids API-Football)
PRIORITY_LEAGUES = {39:0.05, 78:0.05, 140:0.04, 61:0.04, 135:0.03}
SMALL_STADIUMS = ['loftus road','vitality stadium','kenilworth road','turf moor','crowd','bramall lane','ewood park']

# Controle sinais
sent_signals = defaultdict(set)  # fixture_id -> set of keys (HT:4.5, FT:pressure, ...)

# Flask health (opcional)
app = Flask(__name__)

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'})

# ---------- POISSON HELPERS ----------

def poisson_pmf(k: int, lam: float) -> float:
    try:
        if k < 0:
            return 0.0
        return (lam ** k) * math.exp(-lam) / math.factorial(k)
    except Exception:
        return 0.0

def poisson_cdf_le(k: int, lam: float) -> float:
    s = 0.0
    for i in range(0, int(k) + 1):
        s += poisson_pmf(i, lam)
    return s

def poisson_tail_ge(k: int, lam: float) -> float:
    if k <= 0:
        return 1.0
    return 1.0 - poisson_cdf_le(k - 1, lam)

# ---------- API HELPERS ----------

def get_live_fixtures() -> List[Dict[str, Any]]:
    if not API_FOOTBALL_KEY:
        logger.error('API_FOOTBALL_KEY não definida — defina a env var antes de rodar.')
        return []
    urls = [f"{API_BASE}/fixtures?live=all", f"{API_BASE}/fixtures?live=1"]
    for url in urls:
        try:
            r = requests.get(url, headers=HEADERS, timeout=10)
            if r.status_code == 200:
                resp = r.json().get('response', [])
                logger.debug('get_live_fixtures: endpoint %s -> %d fixtures', url, len(resp))
                return resp
            else:
                logger.warning('API-Football fixtures status %s from %s: %.300s', r.status_code, url, r.text)
        except requests.exceptions.RequestException as e:
            logger.exception('Erro ao buscar fixtures (%s): %s', url, e)
    return []

def get_fixture_statistics(fixture_id: int) -> List[Dict[str, Any]]:
    if not API_FOOTBALL_KEY:
        logger.error('API_FOOTBALL_KEY não definida.')
        return []
    try:
        r = requests.get(f"{API_BASE}/fixtures/statistics?fixture={fixture_id}", headers=HEADERS, timeout=10)
        if r.status_code == 200:
            return r.json().get('response', [])
        else:
            logger.warning('API-Football statistics status %s for fixture %s: %.300s', r.status_code, fixture_id, r.text)
    except Exception as e:
        logger.exception('Erro ao buscar statistics: %s', e)
    return []

# ---------- STAT EXTRACTION ----------

def extract_basic_stats(fixture: Dict[str, Any], stats_resp: List[Dict[str, Any]]) -> Tuple[Dict[str,int], Dict[str,int]]:
    """
    Retorna dicts home: {'corners','attacks','danger'} e away similarly.
    Robust parsing (strings, percent, id ou nome).
    """
    teams = fixture.get('teams', {})
    home_id = teams.get('home', {}).get('id')
    away_id = teams.get('away', {}).get('id')

    home = {'corners': 0, 'attacks': 0, 'danger': 0}
    away = {'corners': 0, 'attacks': 0, 'danger': 0}

    for entry in stats_resp or []:
        team = entry.get('team') or {}
        stats_list = entry.get('statistics') or []
        team_id = team.get('id')
        target = None
        if team_id == home_id:
            target = home
        elif team_id == away_id:
            target = away
        else:
            # fallback por nome
            team_name = (team.get('name') or '').lower()
            home_name = (teams.get('home', {}).get('name') or '').lower()
            away_name = (teams.get('away', {}).get('name') or '').lower()
            if team_name and home_name and home_name in team_name:
                target = home
            elif team_name and away_name and away_name in team_name:
                target = away

        if not target:
            continue

        for s in stats_list:
            t = str(s.get('type', '')).lower()
            val = s.get('value')
            try:
                if isinstance(val, str):
                    val = val.replace('%', '').strip()
                val = int(float(val)) if val is not None else 0
            except Exception:
                val = 0

            if 'corner' in t:
                target['corners'] = val
            elif 'attack' in t and 'danger' not in t:
                target['attacks'] = val
            elif 'on goal' in t or 'danger' in t or 'shots on goal' in t or 'shots' in t:
                target['danger'] = val

    return home, away

# ---------- PRESSURE METRIC ----------

def pressure_score(home: Dict[str,int], away: Dict[str,int]) -> Tuple[float, float]:
    h_att = home.get('attacks', 0)
    a_att = away.get('attacks', 0)
    h_d = home.get('danger', 0)
    a_d = away.get('danger', 0)

    if (h_att + a_att) < ATTACKS_MIN:
        return 0.0, 0.0

    att_component = min(1.0, max(0.0, (h_att - a_att) / max(1, ATTACKS_DIFF)))
    dang_component = min(1.0, max(0.0, (h_d - a_d) / max(1, DANGER_DIFF)))
    abs_component = min(1.0, (h_att + h_d) / 20.0)

    score_home = 0.35 * att_component + 0.55 * dang_component + 0.10 * abs_component

    att_component_a = min(1.0, max(0.0, (a_att - h_att) / max(1, ATTACKS_DIFF)))
    dang_component_a = min(1.0, max(0.0, (a_d - h_d) / max(1, DANGER_DIFF)))
    abs_component_a = min(1.0, (a_att + a_d) / 20.0)
    score_away = 0.35 * att_component_a + 0.55 * dang_component_a + 0.10 * abs_component_a

    return score_home, score_away

# ---------- POISSON PREDICTION ----------

def predict_corners_and_line_metrics(current_total_corners: int, lam_remaining: float, candidate_line) -> Dict[str, Any]:
    try:
        is_fractional = isinstance(candidate_line, float) and (candidate_line % 1) != 0
    except Exception:
        is_fractional = False

    if is_fractional:
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

def evaluate_candidate_lines(current_total: int, lam: float, lines_to_check=None) -> List[Dict[str,Any]]:
    if lines_to_check is None:
        lines_to_check = [3.5, 4.0, 4.5, 5.0, 5.5]
    results = []
    for L in lines_to_check:
        m = predict_corners_and_line_metrics(current_total, lam, L)
        results.append(m)
    results.sort(key=lambda x: x['p_win'], reverse=True)
    return results

# ---------- MESSAGE BUILDING & TELEGRAM ----------

def build_vip_message(fixture: Dict[str,Any], window_key: str, metrics: Dict[str,Any], best_lines: List[Dict[str,Any]]) -> str:
    teams = fixture.get('teams', {})
    home = teams.get('home', {}).get('name', 'Home')
    away = teams.get('away', {}).get('name', 'Away')
    league = fixture.get('league', {}).get('name', 'League')
    minute = metrics.get('minute', '?')
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

def send_telegram_message(text: str, parse_mode: str = "HTML") -> bool:
    if not TOKEN or not TELEGRAM_CHAT_ID:
        logger.error('TOKEN ou TELEGRAM_CHAT_ID não definidos — não foi possível enviar mensagem.')
        return False
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True
    }
    try:
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code == 200:
            logger.info('Mensagem enviada para Telegram (chat_id=%s).', TELEGRAM_CHAT_ID)
            return True
        else:
            logger.warning('Falha ao enviar Telegram %s: %s', r.status_code, r.text)
    except Exception as e:
        logger.exception('Erro ao enviar mensagem para Telegram: %s', e)
    return False

# ---------- CORE: análise por fixture ----------

def safe_get_minute(fixture_obj: Dict[str,Any]) -> int:
    # Estruturas variam: fixture_obj pode ser o item de response ou conter 'fixture'
    fix = fixture_obj.get('fixture') or fixture_obj
    status = fix.get('status', {})
    minute = None
    if isinstance(status, dict):
        minute = status.get('elapsed')
    else:
        try:
            minute = int(status)
        except Exception:
            minute = None
    if minute is None:
        # fallback: tente em fixture_obj['fixture']['status']['elapsed']
        try:
            minute = fixture_obj.get('fixture', {}).get('status', {}).get('elapsed')
        except Exception:
            minute = None
    return int(minute) if minute is not None else -1

def estimate_lambda_remaining(current_total_corners: int, elapsed_minute: int, final_minute: int = 90) -> float:
    """
    Estima lambda (cantos esperados nos minutos restantes).
    Estratégia simples e robusta:
    - taxa_per_minuto = current_total / max(1, elapsed_minute)
    - remaining_minutes = max(1, final_minute - elapsed_minute)
    - lam_remaining = taxa_per_minuto * remaining_minutes
    - garante mínimo 0.1 para evitar zeros
    """
    if elapsed_minute <= 0:
        return max(0.1, current_total_corners * 0.5)
    taxa = current_total_corners / max(1.0, float(elapsed_minute))
    remaining = max(1, final_minute - elapsed_minute)
    lam = taxa * remaining
    # pequenos ajustes: se taxa muito baixa, mas estamos vendo muita pressão, poderia aumentar lam
    return max(0.1, lam)

def process_fixture(f: Dict[str,Any]) -> None:
    fix = f.get('fixture') or f
    fixture_id = fix.get('id') or f.get('fixture', {}).get('id')
    league_id = f.get('league', {}).get('id') if f.get('league') else None

    minute = safe_get_minute(f)
    if minute < 0:
        logger.debug('Fixture %s sem minuto válido, pulando.', fixture_id)
        return

    # windows HT/FT check
    window_key = None
    if HT_WINDOW[0] <= minute <= HT_WINDOW[1]:
        window_key = f"HT_{HT_WINDOW[0]}-{HT_WINDOW[1]}"
    elif FT_WINDOW[0] <= minute <= FT_WINDOW[1]:
        window_key = f"FT_{FT_WINDOW[0]}-{FT_WINDOW[1]}"

    # se não está dentro das janelas, ainda processamos (pode querer sinais fora das janelas)
    # pegar stats
    stats = get_fixture_statistics(fixture_id)
    home_stats, away_stats = extract_basic_stats(f, stats)

    # total corners current
    home_corners = home_stats.get('corners', 0)
    away_corners = away_stats.get('corners', 0)
    total_corners = home_corners + away_corners

    # pressure
    score_home, score_away = pressure_score(home_stats, away_stats)
    pressure = False
    leading_side = None
    if score_home >= MIN_PRESSURE_SCORE and score_home > score_away:
        pressure = True
        leading_side = 'home'
    elif score_away >= MIN_PRESSURE_SCORE and score_away > score_home:
        pressure = True
        leading_side = 'away'

    # stadium small?
    venue = f.get('fixture', {}).get('venue', {}).get('name', '') or ''
    small_stadium = any(s in venue.lower() for s in SMALL_STADIUMS)

    # lambda estimate
    lam_remaining = estimate_lambda_remaining(total_corners, minute, final_minute=90)

    # evaluate lines
    best_lines = evaluate_candidate_lines(total_corners, lam_remaining)

    # choose candidate to send: priorize lines with p_win >= threshold and p_push < some threshold
    selected = None
    for ln in best_lines:
        if ln['p_win'] >= PROB_LINE_THRESHOLD and ln['p_push'] <= PROB_PUSH_ALERT:
            selected = ln
            break

    # Add small league bonus: slightly relax threshold for priority leagues
    if not selected and league_id in PRIORITY_LEAGUES:
        relax = PRIORITY_LEAGUES.get(league_id, 0.0)
        for ln in best_lines:
            if ln['p_win'] >= (PROB_LINE_THRESHOLD - relax) and ln['p_push'] <= PROB_PUSH_ALERT + 0.05:
                selected = ln
                break

    # build metrics
    metrics = {
        'minute': minute,
        'home_corners': home_corners,
        'away_corners': away_corners,
        'total_corners': total_corners,
        'home_attacks': home_stats.get('attacks', 0),
        'away_attacks': away_stats.get('attacks', 0),
        'home_danger': home_stats.get('danger', 0),
        'away_danger': away_stats.get('danger', 0),
        'pressure': pressure,
        'leading_side': leading_side,
        'small_stadium': small_stadium,
        'lam_remaining': lam_remaining
    }

    # determine signal key to prevent duplicates
    signal_key = None
    if window_key and selected:
        signal_key = f"{window_key}_L{selected['line']}"
    elif selected:
        signal_key = f"L{selected['line']}"
    elif pressure:
        signal_key = f"PRESS_{leading_side}_{minute}"
    else:
        # nada a enviar
        signal_key = None

    if not signal_key:
        logger.debug('Fixture %s: nenhum sinal identificado (min=%s total_cantos=%s).', fixture_id, minute, total_corners)
        return

    if signal_key in sent_signals.get(fixture_id, set()):
        logger.debug('Fixture %s: sinal %s já enviado antes, pulando.', fixture_id, signal_key)
        return

    # Build and send message
    message = build_vip_message(f, window_key or 'LIVE', metrics, best_lines if best_lines else [])
    ok = send_telegram_message(message)
    if ok:
        sent_signals[fixture_id].add(signal_key)
        logger.info('Sinal enviado para fixture %s: %s', fixture_id, signal_key)
    else:
        logger.warning('Falha ao enviar sinal para fixture %s: %s', fixture_id, signal_key)

# ---------- SMOKE TEST / MAIN LOOP ----------

def smoke_test():
    logger.info('Executando smoke_test() — checando fixtures ao vivo...')
    fixtures = get_live_fixtures()
    if not fixtures:
        logger.warning('Nenhuma partida ao vivo retornada — verifique API key, limite de requests ou bloqueio de IP.')
        print('\nSugestões rápidas para depurar:')
        print('- Confirme que a env var API_FOOTBALL_KEY está definida: echo $API_FOOTBALL_KEY')
        print('- Teste via curl (local): curl -s "https://v3.football.api-sports.io/fixtures?live=all" -H "x-apisports-key: YOUR_KEY"')
        print('- Veja se o status code é 401 (key inválida) ou 429 (rate limit).')
        return
    print(f'Fixtures ao vivo: {len(fixtures)}')
    for i, f in enumerate(fixtures[:10]):
        fix = f.get('fixture') or f
        teams = f.get('teams') or {}
        league = f.get('league',{}).get('name')
        minute = safe_get_minute(f)
        print(f"[{i}] fixture_id: {fix.get('id')} | league: {league} | minute: {minute} | teams: {teams.get('home',{}).get('name')} x {teams.get('away',{}).get('name')}")

def main_loop(iterations: int = 0, delay: int = 20):
    """
    iterations: 0 -> loop infinito
    delay: segundos entre iterações
    """
    logger.info('Iniciando main_loop (iterations=%s delay=%ss)', iterations, delay)
    loop_count = 0
    try:
        while True:
            fixtures = get_live_fixtures()
            if fixtures:
                for f in fixtures:
                    try:
                        process_fixture(f)
                    except Exception as e:
                        logger.exception('Erro ao processar fixture: %s', e)
            else:
                logger.debug('Nenhuma fixture ao vivo no momento.')
            loop_count += 1
            if iterations and loop_count >= iterations:
                logger.info('main_loop finalizando após %d iterações (param iterations=%d).', loop_count, iterations)
                break
            time.sleep(delay)
    except KeyboardInterrupt:
        logger.info('main_loop interrompido pelo usuário.')

# ---------- ENTRYPOINT ----------

if __name__ == '__main__':
    # prints básicos de debug
    logger.info('==== Iniciando bot_escanteios_rp_vip_plus_final ====')
    logger.info('API_FOOTBALL_KEY presente: %s', bool(API_FOOTBALL_KEY))
    logger.info('TOKEN presente: %s', bool(TOKEN))
    logger.info('TELEGRAM_CHAT_ID presente: %s', bool(TELEGRAM_CHAT_ID))
    if not API_FOOTBALL_KEY:
        logger.error('API_FOOTBALL_KEY ausente — não será possível buscar partidas.')
    # Rodar smoke_test primeiro pra você ver o que a API retorna
    smoke_test()
    # Se quiser rodar apenas 1 iteração para teste: main_loop(iterations=1, delay=10)
    # Para produção, use loop infinito:
    main_loop(iterations=0, delay=20)