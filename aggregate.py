"""Orquestrador — gera data.json para o dashboard geral DP100K."""
import json
import os
from datetime import datetime, timezone, timedelta

from fetch_sheets import fetch
from analytics import build_all

HERE = os.path.dirname(__file__)


def _load_json(nome):
    """Enriquecimentos gerados fora do CI (thumbs.json, video.json). Ausente = {}."""
    p = os.path.join(HERE, nome)
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


# Cabeçalhos da planilha `Página1`, na ordem em que pull_adlevel.py grava as colunas.
# Manter esses nomes: é por eles que analytics.build_all lê cada métrica.
ADLEVEL_COLS = [
    "Date", "Campaign Name", "Adset Name", "Ad Name",
    "Spend (Cost, Amount Spent)", "Impressions", "Reach (Estimated)",
    "Action Link Clicks", "Action Landing Page View",
    "Action Omni Initiated Checkout", "Action Omni Purchase",
]


def _merge_adlevel(trafego, adlevel):
    """Troca o tráfego da planilha pelo puxado da Meta nos dias que a API cobre.

    A planilha do n8n congelou em 2026-07-27 e, mesmo viva, só via a conta C1 —
    o que sumia com a Memorável desde 22/07. `pull_adlevel.py` puxa as 2 contas
    direto da Insights e grava adlevel.json. Aqui as linhas dele viram dicts com
    os MESMOS cabeçalhos da planilha, então analytics.py segue igual.

    Dia coberto pela API vence o dia da planilha (não soma — dobraria). Dia fora
    da cobertura continua vindo da planilha, que fica como fallback histórico.
    """
    rows = (adlevel or {}).get("rows") or []
    if not rows:
        print("AVISO: adlevel.json vazio/ausente — tráfego ad-level vindo só da planilha.")
        return trafego
    ads_meta = adlevel.get("ads") or {}
    dias_api = {r[0] for r in rows}
    out = []
    for r in rows:
        d = dict(zip(ADLEVEL_COLS, r))
        m = ads_meta.get(d["Ad Name"]) or ["", "", ""]
        d["Instagram Permalink URL"], d["Preview Shareable Link"], d["Ad Status"] = m
        out.append(d)
    resto = [r for r in trafego if (r.get("Date") or "").strip() not in dias_api]
    ate = max(dias_api)
    print(f"ad-level: {len(out)} linhas da Meta API ({min(dias_api)} a {ate}) "
          f"+ {len(resto)} linhas remanescentes da planilha")
    # adlevel.json é gerado FORA do CI (precisa do token da Meta). Se ninguém rodar
    # pull_adlevel.py, a view Ads / split por funil / hook-hold congelam sem que
    # nada mais no dash pareça errado — foi exatamente assim que a planilha passou
    # 11 dias parada sem ninguém ver. Daí o aviso alto no log do refresh.
    atraso = (datetime.now(timezone(timedelta(hours=-3))).date()
              - datetime.strptime(ate, "%Y-%m-%d").date()).days
    if atraso > 2:
        print(f"AVISO: tráfego ad-level parado há {atraso} dias (último dia {ate}). "
              f"Rodar `/usr/bin/python3 pull_adlevel.py` local e commitar adlevel.json.")
    return out + resto


def main():
    raw = fetch()
    thumbs = _load_json("thumbs.json")
    video = _load_json("video.json")
    trafego = _merge_adlevel(raw["trafego"], _load_json("adlevel.json"))
    data = build_all(trafego, raw["hubla_rows"], raw["invest_rows"],
                     raw["origem_rows"], pesquisa_rows=raw.get("pesquisa_rows"),
                     thumbs=thumbs, video=video)
    data["updated_at"] = datetime.now(timezone(timedelta(hours=-3))).strftime("%Y-%m-%d %H:%M:%S BRT")
    data["schema_version"] = 6  # v6: + métricas de vídeo por ad x dia (hook/hold/retenção)

    # Guarda-corpo: em 28/07/2026 inseriram uma coluna na aba da Hubla, os índices
    # deslizaram e o refresh horário publicou ~14h de dashboard com 0 ingressos sem
    # ninguém perceber. Se a fonte tem linhas e o resultado é zero, é bug — aborta
    # antes de gravar, e o CI mantém o data.json anterior no ar.
    ing_total = sum(x["ing_n"] for x in data["daily"])
    spend_total = sum(x["spend"] for x in data["daily"])
    if ing_total == 0 and len(raw["hubla_rows"]) > 1:
        raise SystemExit(
            f"ABORTADO: 0 ingressos com {len(raw['hubla_rows'])-1} linhas na aba da Hubla. "
            "Provável mudança de coluna na planilha — conferir analytics._hubla_cols()."
        )
    if spend_total == 0:
        raise SystemExit("ABORTADO: investimento total zerado — conferir fontes de tráfego.")
    # Mesma classe de bug na aba ORIGEM DE VENDAS (renomeada em 04/08/2026, header
    # mudou de linha): all-time sempre tem venda de IPM atribuída ao DP100K.
    if sum(x["ipm_n"] for x in data["daily"]) == 0 and len(raw["origem_rows"]) > 1:
        raise SystemExit(
            f"ABORTADO: 0 vendas IPM com {len(raw['origem_rows'])-1} linhas na aba ORIGEM DE VENDAS. "
            "Provável mudança de header/coluna — conferir analytics._origem_header_row()."
        )

    out_path = os.path.join(HERE, "data.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    print(f"data.json: {os.path.getsize(out_path):,} bytes")

    # resumo
    dl = data["daily"]
    tot = lambda k: sum(x[k] for x in dl)
    fat = tot("ing_rev") + tot("ipm_rev") + tot("out_rev")
    print(f"\n=== Resumo ({data['meta']['date_min']} a {data['meta']['date_max']}) ===")
    print(f"  dias:         {len(dl)}")
    print(f"  investimento: R$ {tot('spend'):>12,.2f}")
    _rn, _mq = tot('ing_renda'), tot('ing_mql')
    print(f"  ingressos:    {tot('ing_n'):4d}  (R$ {tot('ing_rev'):,.0f})")
    print(f"  MQL(>=10k):   {_mq:4d}  ({(_mq/_rn*100 if _rn else 0):.1f}% de {_rn} c/ renda; cobertura {(_rn/tot('ing_n')*100 if tot('ing_n') else 0):.0f}%)")
    print(f"  IPM:          {tot('ipm_n'):4d}  (R$ {tot('ipm_rev'):,.0f})")
    print(f"  outras:       {tot('out_n'):4d}  (R$ {tot('out_rev'):,.0f})")
    print(f"  faturamento:  R$ {fat:,.2f}")
    print(f"  ROAS:         {(fat / tot('spend')) if tot('spend') else 0:.2f}x")
    _sp, _ing, _mt = tot('spend'), tot('ing_n'), tot('ing_meta')
    print(f"  CPA geral:    R$ {(_sp/_ing if _ing else 0):>8,.2f}  ({_ing} ingressos, blended)")
    print(f"  CPA Meta Ads: R$ {(_sp/_mt if _mt else 0):>8,.2f}  ({_mt} c/ utm_source=meta_ads, "
          f"{(_mt/_ing*100 if _ing else 0):.1f}% do total)")
    print(f"  turmas:       {len(data['turmas'])}  ({', '.join(t['label'] for t in data['turmas'])})")
    print(f"  ads_daily:    {len(data['ads_daily'])} linhas | ads distintos: {len(data['ads_meta'])}")
    thumbs_ok = sum(1 for m in data["ads_meta"].values() if m.get("thumb"))
    print(f"  thumbs:       {thumbs_ok}/{len(data['ads_meta'])}")
    vid_rows = [r for r in data["ads_daily"] if "v3" in r]
    vid_ads = {r["ad"] for r in vid_rows}
    v3 = sum(r["v3"] for r in vid_rows)
    vimpr = sum(r["impr"] for r in vid_rows)
    p100 = sum(r["p100"] for r in vid_rows)
    print(f"  vídeo:        {len(vid_ads)}/{len(data['ads_meta'])} ads com dado "
          f"({len(vid_rows)} linhas ad x dia) | hook {(v3/vimpr*100 if vimpr else 0):.1f}% "
          f"· hold {(p100/v3*100 if v3 else 0):.1f}%")

    # reconciliação por funil
    print("\n=== Por funil (reconciliação) ===")
    seg = data["seg_daily"]
    tot_spend = tot("spend")
    tot_ing = tot("ing_n")
    ssp = sing = 0.0
    for f in [x["key"] for x in data["funnels"]]:
        sp = sum(x["spend"] for x in seg[f]); ig = sum(x["ing_n"] for x in seg[f])
        igr = sum(x["ing_rev"] for x in seg[f])
        ssp += sp; sing += ig
        pct = (sp / tot_spend * 100) if tot_spend else 0
        print(f"  {f:16s} spend R$ {sp:>10,.0f} ({pct:4.1f}%) | ingressos {ig:4d} (R$ {igr:,.0f})")
    print(f"  {'SOMA funis':16s} spend R$ {ssp:>10,.0f} / total R$ {tot_spend:,.0f}  (dif R$ {tot_spend-ssp:,.2f})")
    print(f"  ingressos atribuídos: {int(sing)}/{tot_ing}  (orgânico/CRM/IPM fora dos funis pagos: {tot_ing-int(sing)})")

    # reconciliação do join venda x criativo (o que aparece nos cards de Ads)
    ads_names = {a.lower() for a in data["ads_meta"]}
    ha = data["hubla_ads_daily"]
    casadas = sum(x["ing"] for x in ha if x["k"] in ads_names)
    orfas = sum(x["ing"] for x in ha if x["k"] not in ads_names)
    print("\n=== Join venda x criativo (view Ads) ===")
    print(f"  vendas com utm de ad:  {casadas + orfas}")
    print(f"  casam com um card:     {casadas}")
    print(f"  órfãs (sem card):      {orfas}  (ad de outro funil ou já removido)")
    print(f"  sem utm de ad:         {tot_ing - casadas - orfas}  (orgânico/CRM/macro)")


if __name__ == "__main__":
    main()
