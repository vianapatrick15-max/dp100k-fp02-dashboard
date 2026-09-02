"""Enriquecimento (rodar local/manual) — puxa métricas de VÍDEO por anúncio x dia
via Meta Insights API e grava video.json. O aggregate.py mescla isso no ads_daily,
e a view Ads calcula hook rate / hold rate / curva de retenção.

Por que não vem da planilha: a coleta do n8n (Página1) só exporta 'Action Video
View' agregado — não tem os quartis (p25/p50/p75/p100) nem plays. Sem quartil não
dá pra saber ONDE o criativo perde a audiência, que é o ponto todo da leitura.

Métricas guardadas por (ad, dia):
  v3    actions[video_view]              visualizações de 3s  -> numerador do HOOK
  p25/p50/p75/p100                        quartis assistidos   -> curva de retenção
  thru  video_thruplay_watched_actions   ThruPlay (15s ou fim)
  plays video_play_actions               plays iniciados (não usado na UI, guardado p/ auditoria)

Fórmulas na UI (definidas aqui de propósito, pra não ficar ambíguo):
  HOOK RATE = v3 / impressões        quantos pararam o scroll
  HOLD RATE = p100 / v3              dos que pararam, quantos foram até o fim

Uso:
  /usr/bin/python3 pull_video.py                # incremental (últimos 4 dias + o que faltar)
  /usr/bin/python3 pull_video.py --since 2026-01-01   # janela explícita
  /usr/bin/python3 pull_video.py --full         # tudo desde ADS_SINCE

Requer: facebook_business + python-dotenv + token em ~/.claude/skills/meta-ads-memoravel/.env
Não roda no CI (o refresh horário só relê o video.json já commitado).
"""
import os
import sys
import json
from datetime import date, datetime, timedelta

from dotenv import load_dotenv

load_dotenv(os.path.expanduser("~/.claude/skills/meta-ads-memoravel/.env"))
from facebook_business.api import FacebookAdsApi
from facebook_business.adobjects.adaccount import AdAccount

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "video.json")

ADS_SINCE = "2026-01-01"          # mesmo corte do ads_daily em analytics.py
LOOKBACK_DAYS = 4                 # Meta ainda revisa números de dias recentes

# Os ads do DP100K vivem em duas contas desde 22/07/2026 (ver memória
# project_dp100k_fp02_dashboard): C1 Instituto e Memorável.
ACCOUNTS = [
    ("act_1725623984282551", "C1 Instituto"),
    ("act_1835702343244302", "Memorável"),
    # 27/08/2026: DP100K migrou pra C4 — sem ela o ad-level congela nessa data
    ("act_1631219441753243", "C4 Memorável"),
]

FIELDS = [
    "ad_name", "impressions", "actions", "video_play_actions",
    "video_thruplay_watched_actions", "video_p25_watched_actions",
    "video_p50_watched_actions", "video_p75_watched_actions",
    "video_p100_watched_actions",
]
FILTER = [{"field": "ad.name", "operator": "CONTAIN", "value": "DP100K"}]

# ordem dos valores gravados no video.json (lista, não dict, pra não inchar o arquivo)
SLOTS = ("v3", "p25", "p50", "p75", "p100", "thru", "plays")


def _av(row, key):
    """Campo de vídeo da API vem como [{'action_type':'video_view','value':'309'}]."""
    v = row.get(key)
    if not v:
        return 0
    try:
        return int(float(v[0].get("value", 0)))
    except Exception:
        return 0


def _action(row, action_type):
    for a in row.get("actions") or []:
        if a.get("action_type") == action_type:
            try:
                return int(float(a.get("value", 0)))
            except Exception:
                return 0
    return 0


def _months(since, until):
    """Fatia o período em blocos mensais — puxar 7 meses de ad x dia num request só
    estoura o limite da API e volta 500."""
    a = datetime.strptime(since, "%Y-%m-%d").date()
    b = datetime.strptime(until, "%Y-%m-%d").date()
    out = []
    while a <= b:
        nxt = (a.replace(day=1) + timedelta(days=32)).replace(day=1)
        out.append((a.isoformat(), min(b, nxt - timedelta(days=1)).isoformat()))
        a = nxt
    return out


def main():
    args = sys.argv[1:]
    data = {}
    if os.path.exists(OUT):
        try:
            with open(OUT, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}

    hoje = date.today().isoformat()
    if "--full" in args or not data:
        since = ADS_SINCE
    elif "--since" in args:
        since = args[args.index("--since") + 1]
    else:
        vistos = sorted({d for dias in data.values() for d in dias})
        ultimo = vistos[-1] if vistos else ADS_SINCE
        since = min(
            ultimo,
            (date.today() - timedelta(days=LOOKBACK_DAYS)).isoformat(),
        )
    print(f"janela: {since} -> {hoje}  (video.json tinha {len(data)} ads)", file=sys.stderr)

    FacebookAdsApi.init(
        app_id=os.getenv("META_APP_ID"),
        access_token=os.getenv("META_ADS_TOKEN"),
        api_version="v21.0",
    )

    novos = 0
    for acc, apelido in ACCOUNTS:
        vistos_acc = 0
        for ini, fim in _months(since, hoje):
            params = {
                "level": "ad",
                "time_increment": 1,
                "time_range": {"since": ini, "until": fim},
                "filtering": FILTER,
                "limit": 200,
            }
            try:
                it = AdAccount(acc).get_insights(fields=FIELDS, params=params)
                for r in it:
                    vistos_acc += 1
                    nome = (r.get("ad_name") or "").strip()
                    d = r.get("date_start")
                    if not nome or not d:
                        continue
                    vals = [
                        _action(r, "video_view"),
                        _av(r, "video_p25_watched_actions"),
                        _av(r, "video_p50_watched_actions"),
                        _av(r, "video_p75_watched_actions"),
                        _av(r, "video_p100_watched_actions"),
                        _av(r, "video_thruplay_watched_actions"),
                        _av(r, "video_play_actions"),
                    ]
                    if not any(vals):
                        continue        # estático: nada de vídeo pra guardar
                    dias = data.setdefault(nome, {})
                    if d in dias:
                        # mesmo ad rodando nas duas contas no mesmo dia -> soma
                        dias[d] = [x + y for x, y in zip(dias[d], vals)]
                    else:
                        dias[d] = vals
                        novos += 1
            except Exception as e:
                print(f"  {apelido} {ini}..{fim}: ERRO {str(e)[:120]}", file=sys.stderr)
                continue
        print(f"  {apelido}: {vistos_acc} linhas ad x dia", file=sys.stderr)

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))

    linhas = sum(len(v) for v in data.values())
    tot = {k: 0 for k in SLOTS}
    for dias in data.values():
        for v in dias.values():
            for i, k in enumerate(SLOTS):
                tot[k] += v[i]
    print(f"\nvideo.json: {len(data)} ads / {linhas} linhas ad x dia "
          f"(+{novos} novas) / {os.path.getsize(OUT):,} bytes", file=sys.stderr)
    print(f"  3s {tot['v3']:,} · p25 {tot['p25']:,} · p50 {tot['p50']:,} · "
          f"p75 {tot['p75']:,} · p100 {tot['p100']:,} · thru {tot['thru']:,}", file=sys.stderr)


if __name__ == "__main__":
    main()
