# bot.py
# Bot de sinais de escanteios (HT 30-38 / FT 80-88)
# Substitua API_KEY pelo seu valor (API-Football / API-Sports)
# Se usar RapidAPI (api-football via RapidAPI) veja comentário abaixo.

import time
import requests
import traceback
from datetime import datetime, timedelta

# ========== CONFIGURAÇÃO ==========
TOKEN = "7977015488:AAFdpmpZE-6O0V-wIJnUa5UQu3Osil-lzEI"  # seu token Telegram
CHAT_ID = "7400926391"  # seu chat id

API_KEY = "d6fec5cd6cmsh108e41f6f563c21p140d1fjsnaee05756c8a8"  # <<< cole sua API key aqui
# Se usar API via RapidAPI (rapidapi.com/api-sports/api/api-football)
# substitua/adicione os headers abaixo e comente a linha headers['x-apisports-key']:
# headers = {
#    "x-rapidapi-key": "SUA_RAPIDAPI_KEY",
#    "x-rapidapi-host": "v3.football.api-sports.io"
# }
BASE_URL = "https://v3.football.api-sports.io"  # endpoint comum da API-Football (api-sports)

# Parâmetros da estratégia / análise
POLL_INTERVAL = 15  # segundos entre checagens (quando vivo)
N_LAST = 10  # número de jogos passados para calcular média de corners
MIN_AVG_CORNERS = 9.0  # média combinada mínima (timeA.avg + timeB.avg) para filtrar "alto índice"
HT_WINDOW = (30, 38)  # minutos inclusivos para HT signal
FT_WINDOW = (80, 88)  # minutos inclusivos para FT signal

# Controle para não enviar duplicados: armazenará tuples (fixture_id, strategy_tag)
SENT_SIGNALS = set()

# Cabeçalhos de autenticação padrão pra API-Football (api-sports)
headers = {
    "x-apisports-key": API_KEY,
    "Accept": "application/json"
}

# ======== UTILIDADES ========
def enviar_mensagem(mensagem):
    if TOKEN.startswith("SEU_TOKEN") or CHAT_ID.startswith("SEU_CHAT_ID"):
        print("⚠️ ATENÇÃO: configure TOKEN e CHAT_ID no arquivo.")
        return
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    dados = {"chat_id": CHAT_ID, "text": mensagem, "parse_mode":"HTML"}
    try:
        resp = requests.post(url, data=dados, timeout=10)
        if not resp.ok:
            print(f"Erro ao enviar mensagem: HTTP {resp.status_code} - {resp.text}")
    except requests.exceptions.RequestException as e:
        print("Erro ao enviar mensagem:", e)
        traceback.print_exc()

def safe_get(url, params=None):
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=10)
        if resp.ok:
            return resp.json()
        else:
            print("Erro HTTP", resp.status_code, resp.text)
            return None
    except Exception as e:
        print("Exception safe_get:", e)
        return None

# ======== FUNÇÕES DE DADOS ========
def get_live_fixtures():
    """
    Retorna lista de fixtures ao vivo.
    Tenta alguns parâmetros comumente suportados (status=LIVE / live=all).
    """
    endpoints = [
        (f"{BASE_URL}/fixtures", {"status":"LIVE"}),     # comum: ?status=LIVE
        (f"{BASE_URL}/fixtures", {"live":"all"}),       # alternativa: ?live=all
    ]
    for url, params in endpoints:
        data = safe_get(url, params=params)
        if data and isinstance(data, dict):
            # a API retorna normalmente chave 'response' com lista
            if "response" in data and isinstance(data["response"], list):
                return data["response"]
            # fallback: se estrutura diferente, tentar extrair lista direta
            if isinstance(data.get("response"), list):
                return data.get("response", [])
    return []

def get_fixture_events(fixture_id):
    """ Puxa eventos do jogo (corner events podem estar aqui). """
    url = f"{BASE_URL}/fixtures/events"
    params = {"fixture": fixture_id}
    data = safe_get(url, params=params)
    if data and "response" in data:
        return data["response"]
    return []

def get_fixture_statistics(fixture_id):
    """ Puxa estatísticas do jogo (pode incluir corners por time). """
    url = f"{BASE_URL}/fixtures/statistics"
    params = {"fixture": fixture_id}
    data = safe_get(url, params=params)
    if data and "response" in data:
        return data["response"]
    return []

def get_team_last_fixtures(team_id, last=N_LAST):
    """ Pega últimos jogos do time para calcular média de corners históricos. """
    url = f"{BASE_URL}/fixtures"
    params = {"team": team_id, "last": last}
    data = safe_get(url, params=params)
    if data and "response" in data:
        return data["response"]
    return []

def avg_corners_for_team(team_id):
    """
    Calcula média de escanteios do time nas últimas N_LAST partidas.
    Tenta extrair de 'statistics' do fixture ou de eventos.
    """
    fixtures = get_team_last_fixtures(team_id, last=N_LAST)
    if not fixtures:
        return 0.0
    total_corners = 0
    counted = 0
    for f in fixtures:
        fid = f.get("fixture", {}).get("id") or f.get("id")  # suportar formatos
        if not fid:
            continue
        stats = get_fixture_statistics(fid)
        # stats normalmente é uma lista com dois objetos (time A, time B)
        if stats:
            # procurar item com 'type' == 'Corners' ou nome parecido
            for team_stats in stats:
                # team_stats pode ser dict com 'team' e 'statistics' ou similar
                stats_list = team_stats.get("statistics") if isinstance(team_stats, dict) else None
                if not stats_list and isinstance(team_stats, list):
                    stats_list = team_stats
                # procurar 'Corners' no stats_list
                if stats_list:
                    for s in stats_list:
                        label = s.get("type") or s.get("name") or s.get("statistic")
                        if label and ("corner" in str(label).lower()):
                            # valor pode estar em 'value'
                            val = s.get("value") or s.get("count") or s.get("total")
                            try:
                                total_corners += int(val)
                            except:
                                pass
                            counted += 1
                            break
        # se não encontrou via statistics, fallback: tentar events e contar 'Corner'
        if counted == 0:
            events = get_fixture_events(fid)
            corners = 0
            for ev in events:
                if isinstance(ev, dict):
                    if "type" in ev and ev["type"].lower() == "corner":
                        corners += 1
                    # em algumas APIs 'detail' ou 'event' contém 'Corner'
                    if "detail" in ev and "corner" in str(ev["detail"]).lower():
                        corners += 1
            if corners:
                total_corners += corners
                counted += 1
    if counted == 0:
        return 0.0
    return total_corners / counted

def get_team_position_in_league(league_id, season, team_id):
    """
    Busca tabela/standings para pegar posição do time.
    Pode falhar se a API não permitir sem subscription.
    """
    url = f"{BASE_URL}/standings"
    params = {"league": league_id, "season": season}
    data = safe_get(url, params=params)
    if not data or "response" not in data:
        return None
    for entry in data["response"]:
        # Strutura comum: response -> [ { "league": {...}, "standings": [ [ {team, rank}, ... ] ] } ]
        standings_outer = entry.get("league") or entry.get("standings") or None
        # procurar dentro de 'entry' estruturas 'standings' com listas
        if "standings" in entry:
            for group in entry["standings"]:
                for row in group:
                    tid = row.get("team", {}).get("id") or row.get("team_id")
                    if tid and int(tid) == int(team_id):
                        return row.get("rank") or row.get("position") or row.get("note") or None
    return None

# ======== LÓGICA DE DECISÃO E ENVIO =========
def build_bet365_link(home, away):
    """
    Gera um link prático/fallback para abrir a Bet365 para pesquisa do jogo.
    Obs: deep-links exatos da Bet365 podem exigir mapping com bookmaker API ou event id.
    Aqui geramos um link-inicial para a home da Bet365 + sugestão de busca por nomes.
    """
    # colocar nomes em uma versão "segura" para URL
    q = f"{home} vs {away}"
    # link fallback (home) — o usuário abre e busca pelo jogo
    base = "https://www.bet365.com"
    # tentar um "search-like" (não oficial) — pode não funcionar para todos
    search_like = f"{base}/#/search?q={requests.utils.quote(q)}"
    # também incluir home (se search_like não abrir direto)
    return f"{search_like} \n{base} (se o search não funcionar, busque pelo jogo dentro do site)"

def evaluate_and_send_signals():
    live = get_live_fixtures()
    if not live:
        print(f"[{datetime.utcnow()}] Nenhum jogo ao vivo no momento.")
        return

    for item in live:
        # Estrutura varia: a API costuma ter cada item em item['fixture'] e item['teams'], ...
        fixture = item.get("fixture") or item
        teams = item.get("teams") or item.get("teams", {})
        league = item.get("league") or item.get("league", {})
        fixture_id = fixture.get("id") or fixture.get("fixture_id") or item.get("id")
        if not fixture_id:
            continue

        # pegar minuto se disponível
        status = fixture.get("status") or {}
        minute = None
        # estrutura comum: status -> {"elapsed": 34, "long": "Match Live", ...}
        if isinstance(status, dict):
            minute = status.get("elapsed") or status.get("minute") or None

        # times e placar
        home = (item.get("teams") or {}).get("home", {}).get("name") or (item.get("teams", {}) or {}).get("home") or item.get("teams", {}).get("home", {}).get("name") if item.get("teams") else (item.get("teams", {}) )
        away = (item.get("teams") or {}).get("away", {}).get("name") or item.get("teams", {}).get("away") if item.get("teams") else None

        # placar
        score = item.get("score") or {}
        fullscore = (score.get("fulltime") if isinstance(score.get("fulltime"), dict) else score.get("fulltime")) or score.get("ft") or score.get("full')", None)
        # fallback simpler
        try:
            home_score = item.get("goals", {}).get("home") or score.get("halftime", {}).get("home") if score else None
        except:
            home_score = None
        # Montar minuto e checar janelas
        if minute is None:
            # tentar extrair de item diretamente (estruturas variam)
            minute = item.get("time") or item.get("elapsed") or None

        try:
            minute_int = int(minute) if minute is not None else None
        except:
            minute_int = None

        # Procurar somente se minuto conhecido e dentro das janelas
        if minute_int is None:
            continue

        # Estratégia HT
        if HT_WINDOW[0] <= minute_int <= HT_WINDOW[1]:
            tag = (fixture_id, "HT")
            if tag in SENT_SIGNALS:
                continue
            # calcular médias históricas
            # precisamos dos ids dos times
            team_home_id = (item.get("teams") or {}).get("home", {}).get("id") or item.get("teams", {}).get("home", {}).get("id")
            team_away_id = (item.get("teams") or {}).get("away", {}).get("id") or item.get("teams", {}).get("away", {}).get("id")
            avg_home = avg_corners_for_team(team_home_id) if team_home_id else 0.0
            avg_away = avg_corners_for_team(team_away_id) if team_away_id else 0.0
            combined_avg = avg_home + avg_away
            print(f"Fixture {fixture_id} HT minute {minute_int} combined_avg={combined_avg:.2f}")
            if combined_avg >= MIN_AVG_CORNERS:
                # tentar pegar posição na tabela
                league_id = league.get("id") if isinstance(league, dict) else None
                season = league.get("season") if isinstance(league, dict) else None
                pos_home = get_team_position_in_league(league_id, season, team_home_id) if league_id and season and team_home_id else "N/A"
                pos_away = get_team_position_in_league(league_id, season, team_away_id) if league_id and season and team_away_id else "N/A"
                link = build_bet365_link(home, away)
                mensagem = (
                    f"🚩 <b>Estratégia:</b> HT (30-38) — Probabilidade de +1/2 corners\n"
                    f"🏟️ <b>Jogo:</b> {home} x {away}\n"
                    f"📊 <b>Posições:</b> {home} ({pos_home}) vs {away} ({pos_away})\n"
                    f"⏱️ <b>Minuto:</b> {minute_int}\'\n"
                    f"📈 <b>Média histórica (ult {N_LAST}):</b> {avg_home:.1f} / {avg_away:.1f} (comb: {combined_avg:.1f})\n"
                    f"🔗 <b>Bet365:</b> {link}\n"
                    f"🔎 <i>Filtragem: jogos com maior índice de corners — independente da liga</i>"
                )
                enviar_mensagem(mensagem)
                SENT_SIGNALS.add(tag)

        # Estratégia FT
        elif FT_WINDOW[0] <= minute_int <= FT_WINDOW[1]:
            tag = (fixture_id, "FT")
            if tag in SENT_SIGNALS:
                continue
            team_home_id = (item.get("teams") or {}).get("home", {}).get("id")
            team_away_id = (item.get("teams") or {}).get("away", {}).get("id")
            avg_home = avg_corners_for_team(team_home_id) if team_home_id else 0.0
            avg_away = avg_corners_for_team(team_away_id) if team_away_id else 0.0
            combined_avg = avg_home + avg_away
            print(f"Fixture {fixture_id} FT minute {minute_int} combined_avg={combined_avg:.2f}")
            if combined_avg >= MIN_AVG_CORNERS:
                league_id = league.get("id") if isinstance(league, dict) else None
                season = league.get("season") if isinstance(league, dict) else None
                pos_home = get_team_position_in_league(league_id, season, team_home_id) if league_id and season and team_home_id else "N/A"
                pos_away = get_team_position_in_league(league_id, season, team_away_id) if league_id and season and team_away_id else "N/A"
                link = build_bet365_link(home, away)
                mensagem = (
                    f"🚩 <b>Estratégia:</b> FT (80-88) — Prob. de +1 corner\n"
                    f"🏟️ <b>Jogo:</b> {home} x {away}\n"
                    f"📊 <b>Posições:</b> {home} ({pos_home}) vs {away} ({pos_away})\n"
                    f"⏱️ <b>Minuto:</b> {minute_int}\'\n"
                    f"📈 <b>Média histórica (ult {N_LAST}):</b> {avg_home:.1f} / {avg_away:.1f} (comb: {combined_avg:.1f})\n"
                    f"🔗 <b>Bet365:</b> {link}\n"
                )
                enviar_mensagem(mensagem)
                SENT_SIGNALS.add(tag)

def main_loop():
    print("🤖 Bot de sinais iniciado (monitorando ao vivo)...")
    try:
        while True:
            try:
                evaluate_and_send_signals()
            except Exception as e:
                print("Erro durante evaluate_and_send_signals:", e)
                traceback.print_exc()
            time.sleep(POLL_INTERVAL)
    except KeyboardInterrupt:
        print("Bot interrompido.")

if __name__ == "__main__":
    main_loop()