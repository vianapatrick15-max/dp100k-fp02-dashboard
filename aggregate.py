"""Orquestrador — gera data.json para o dashboard geral DP100K."""
import json
import os
from datetime import datetime, timezone, timedelta

from fetch_sheets import fetch
from analytics import build_all

HERE = os.path.dirname(__file__)


def _load_thumbs():
    p = os.path.join(HERE, "thumbs.json")
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def main():
    raw = fetch()
    thumbs = _load_thumbs()
    data = build_all(raw["trafego"], raw["hubla_rows"], raw["invest_rows"],
                     raw["origem_rows"], thumbs=thumbs)
    data["updated_at"] = datetime.now(timezone(timedelta(hours=-3))).strftime("%Y-%m-%d %H:%M:%S BRT")
    data["schema_version"] = 4  # v4: dash geral (vendas ingresso+IPM+outras / tráfego diário / ads)

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
    print(f"  ingressos:    {tot('ing_n'):4d}  (R$ {tot('ing_rev'):,.0f})")
    print(f"  IPM:          {tot('ipm_n'):4d}  (R$ {tot('ipm_rev'):,.0f})")
    print(f"  outras:       {tot('out_n'):4d}  (R$ {tot('out_rev'):,.0f})")
    print(f"  faturamento:  R$ {fat:,.2f}")
    print(f"  ROAS:         {(fat / tot('spend')) if tot('spend') else 0:.2f}x")
    print(f"  turmas:       {len(data['turmas'])}  ({', '.join(t['label'] for t in data['turmas'])})")
    print(f"  ads_daily:    {len(data['ads_daily'])} linhas | ads distintos: {len(data['ads_meta'])}")
    thumbs_ok = sum(1 for m in data["ads_meta"].values() if m.get("thumb"))
    print(f"  thumbs:       {thumbs_ok}/{len(data['ads_meta'])}")

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


if __name__ == "__main__":
    main()
