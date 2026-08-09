"""Enriquecimento (rodar local/manual) — puxa o TRÁFEGO AD-LEVEL direto da Meta
Insights nas 2 contas e grava adlevel.json. Substitui a planilha `Página1`.

Por que existe: a planilha ad-level do n8n (1R2MdILm.../Página1) congelou em
2026-07-27 e, mesmo viva, só cobria a conta C1 Instituto — desde 22/07 parte do
DP100K roda na Memorável e ficava invisível na view Ads / split por funil / nas
colunas de volume (impr, CPM, alcance, cliques, LPV, IC).

Conferido em 07/08/2026 na janela 20-27/07 (só C1, pra comparar com a planilha):
  spend  API 16.305,51  ==  planilha 16.305,51   (exato)
  cliques 2.327 == 2.327 · impressões 190.814 vs 190.812 · LPV 2.202 vs 2.198
  (diferença de unidades = revisão normal da Meta em dias já fechados)
A Memorável soma outros R$ 5.283,62 na mesma janela, que a planilha não tinha.

Formato do arquivo (compacto de propósito — vai commitado no repo):
  {"rows": [[data, camp, adset, ad, spend, impr, reach, lclk, lpv, ic, purch], ...],
   "ads":  {ad_name: [instagram_permalink, preview_link, status]},
   "cobertura": {"since": ..., "until": ...}}
Números saem em formato BR (vírgula decimal) porque quem lê é o mesmo
`config.parse_money`/`parse_num` que lia a planilha — `aggregate._merge_adlevel`
remonta as linhas com os MESMOS cabeçalhos da planilha, então `analytics` não
sabe (nem precisa saber) de onde veio o dado.

Uso:
  /usr/bin/python3 pull_adlevel.py                 # incremental (últimos 7 dias + buraco)
  /usr/bin/python3 pull_adlevel.py --since 2026-07-01
  /usr/bin/python3 pull_adlevel.py --full          # tudo desde FULL_SINCE
  /usr/bin/python3 pull_adlevel.py --no-meta       # pula a varredura de ads (permalink/status)

Requer: facebook_business + python-dotenv + token em ~/.claude/skills/meta-ads-memoravel/.env
Não roda no CI (o refresh horário só relê o adlevel.json já commitado).
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
OUT = os.path.join(HERE, "adlevel.json")

FULL_SINCE = "2025-09-24"   # primeiro dia que a planilha tinha; mantém o histórico igual
LOOKBACK_DAYS = 7           # Meta revisa números de dias recentes

ACCOUNTS = [
    ("act_1725623984282551", "C1 Instituto"),
    ("act_1835702343244302", "Memorável"),
]

FIELDS = ["campaign_name", "adset_name", "ad_name", "spend",
          "impressions", "reach", "actions"]
# Filtro no nome da CAMPANHA (não do ad): é o mesmo recorte que analytics.py faz
# ao ler a planilha ("dp100k" in campaign_name), então o total fecha.
FILTER = [{"field": "campaign.name", "operator": "CONTAIN", "value": "DP100K"}]

ACTIONS = (("lclk", "link_click"), ("lpv", "landing_page_view"),
           ("ic", "omni_initiated_checkout"), ("purch", "omni_purchase"))


def _br(v, casas=2):
    """14997.0 -> '14997,00' (o parser do dashboard é BR: vírgula é decimal)."""
    return f"{v:.{casas}f}".replace(".", ",")


def _action(row, action_type):
    for a in row.get("actions") or []:
        if a.get("action_type") == action_type:
            try:
                return float(a.get("value", 0))
            except Exception:
                return 0.0
    return 0.0


def _months(since, until):
    """Fatia em blocos mensais — 11 meses de ad x dia num request só estoura."""
    a = datetime.strptime(since, "%Y-%m-%d").date()
    b = datetime.strptime(until, "%Y-%m-%d").date()
    out = []
    while a <= b:
        nxt = (a.replace(day=1) + timedelta(days=32)).replace(day=1)
        out.append((a.isoformat(), min(b, nxt - timedelta(days=1)).isoformat()))
        a = nxt
    return out


def _pull_insights(since, until):
    """(data, camp, adset, ad) -> [spend, impr, reach, lclk, lpv, ic, purch], somando as contas."""
    acc_rows = {}
    for acc, apelido in ACCOUNTS:
        vistos = 0
        for ini, fim in _months(since, until):
            params = {
                "level": "ad",
                "time_increment": 1,
                "time_range": {"since": ini, "until": fim},
                "filtering": FILTER,
                "limit": 300,
            }
            try:
                for r in AdAccount(acc).get_insights(fields=FIELDS, params=params):
                    d = r.get("date_start")
                    ad = (r.get("ad_name") or "").strip()
                    if not d or not ad:
                        continue
                    vistos += 1
                    k = (d, (r.get("campaign_name") or "").strip(),
                         (r.get("adset_name") or "").strip(), ad)
                    vals = [float(r.get("spend") or 0), float(r.get("impressions") or 0),
                            float(r.get("reach") or 0)] + [_action(r, t) for _, t in ACTIONS]
                    cur = acc_rows.get(k)
                    acc_rows[k] = vals if cur is None else [x + y for x, y in zip(cur, vals)]
            except Exception as e:
                print(f"  {apelido} {ini}..{fim}: ERRO {str(e)[:140]}", file=sys.stderr)
                continue
        print(f"  {apelido}: {vistos} linhas ad x dia", file=sys.stderr)
    return acc_rows


def _pull_ads_meta():
    """permalink do Instagram + link de preview + status, por nome de anúncio.

    Vem do objeto Ad (não do Insights). O permalink é o que o dashboard claro usa
    pra embedar o post — sem ele o card cai no thumb estático.
    """
    meta = {}
    campos = ["name", "effective_status", "preview_shareable_link",
              "creative{instagram_permalink_url}"]
    filtro = [{"field": "name", "operator": "CONTAIN", "value": "DP100K"}]
    for acc, apelido in ACCOUNTS:
        n = 0
        try:
            for ad in AdAccount(acc).get_ads(fields=campos,
                                             params={"limit": 50, "filtering": filtro}):
                nome = (ad.get("name") or "").strip()
                if not nome:
                    continue
                n += 1
                cr = ad.get("creative") or {}
                novo = [cr.get("instagram_permalink_url") or "",
                        ad.get("preview_shareable_link") or "",
                        ad.get("effective_status") or ""]
                antigo = meta.get(nome)
                # Mesmo nome em 2 contas: fica o que tem permalink.
                if antigo and antigo[0] and not novo[0]:
                    continue
                meta[nome] = novo
        except Exception as e:
            print(f"  {apelido}: ERRO na varredura de ads {str(e)[:140]}", file=sys.stderr)
            continue
        print(f"  {apelido}: {n} ads DP100K", file=sys.stderr)
    return meta


def main():
    args = sys.argv[1:]
    antigo = {}
    if os.path.exists(OUT):
        try:
            with open(OUT, encoding="utf-8") as f:
                antigo = json.load(f)
        except Exception:
            antigo = {}

    hoje = date.today().isoformat()
    rows_antigas = antigo.get("rows") or []
    if "--full" in args or not rows_antigas:
        since = FULL_SINCE
    elif "--since" in args:
        since = args[args.index("--since") + 1]
    else:
        ultimo = max(r[0] for r in rows_antigas)
        since = min(ultimo, (date.today() - timedelta(days=LOOKBACK_DAYS)).isoformat())

    print(f"janela: {since} -> {hoje}  (adlevel.json tinha {len(rows_antigas)} linhas)",
          file=sys.stderr)

    FacebookAdsApi.init(
        app_id=os.getenv("META_APP_ID"),
        access_token=os.getenv("META_ADS_TOKEN"),
        api_version="v21.0",
    )

    novas = _pull_insights(since, hoje)
    if not novas:
        sys.exit("ABORTADO: a API não devolveu nenhuma linha — adlevel.json mantido como estava.")

    # As linhas da janela nova substituem por completo as antigas do mesmo período
    # (a Meta revisa dias já fechados; somar duplicaria).
    linhas = [r for r in rows_antigas if r[0] < since]
    for (d, camp, adset, ad), v in sorted(novas.items()):
        if v[0] == 0 and v[1] == 0:
            continue          # ad sem gasto e sem impressão no dia: não vira linha
        linhas.append([d, camp, adset, ad, _br(v[0]),
                       str(int(round(v[1]))), str(int(round(v[2]))),
                       str(int(round(v[3]))), str(int(round(v[4]))),
                       str(int(round(v[5]))), str(int(round(v[6])))])
    linhas.sort(key=lambda r: (r[0], r[3]))

    ads_meta = dict(antigo.get("ads") or {})
    if "--no-meta" not in args:
        print("varrendo ads (permalink/preview/status)...", file=sys.stderr)
        ads_meta.update(_pull_ads_meta())

    datas = [r[0] for r in linhas]
    saida = {
        "rows": linhas,
        "ads": ads_meta,
        "cobertura": {"since": min(datas), "until": max(datas)},
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(saida, f, ensure_ascii=False, separators=(",", ":"))

    tot = lambda i: sum(float(r[i].replace(",", ".")) for r in linhas)
    com_link = sum(1 for v in ads_meta.values() if v[0])
    print(f"\nadlevel.json: {len(linhas)} linhas ({min(datas)} a {max(datas)}) / "
          f"{os.path.getsize(OUT):,} bytes", file=sys.stderr)
    print(f"  investimento R$ {tot(4):,.2f} · impressões {tot(5):,.0f} · "
          f"cliques {tot(7):,.0f} · LPV {tot(8):,.0f} · compras {tot(10):,.0f}",
          file=sys.stderr)
    print(f"  ads com permalink: {com_link}/{len(ads_meta)}", file=sys.stderr)


if __name__ == "__main__":
    main()
