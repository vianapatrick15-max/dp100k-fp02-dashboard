"""Orquestrador — gera data.json para o dashboard."""
import json
import os
from datetime import datetime, timezone, timedelta

from fetch_sheets import fetch
from analytics import build_all


def main():
    raw = fetch()
    data = build_all(raw['trafego'], raw['hubla'], raw['pesquisa'])
    data['updated_at'] = datetime.now(timezone(timedelta(hours=-3))).strftime('%Y-%m-%d %H:%M:%S BRT')
    data['schema_version'] = 1

    out_path = os.path.join(os.path.dirname(__file__), 'data.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    size = os.path.getsize(out_path)
    print(f"data.json: {size:,} bytes")

    # resumo rapido
    print("\n=== Resumo ===")
    mes = data['periodos']['mes']
    print(f"MES (28/04-25/05)")
    print(f"  spend:  R$ {mes['trafego']['spend']:>10,.2f}")
    print(f"  purch:  {mes['trafego']['purch']:>4d}  CPA R$ {mes['trafego']['cpa']:>7,.2f}  ROAS {mes['trafego']['roas']:.2f}")
    print(f"  hubla:  total {mes['hubla']['total']:3d} | meta {mes['hubla']['meta_ads']:3d} ({mes['hubla']['pct_meta']:.0f}%)")
    print(f"  pesq :  total {mes['pesquisa']['total']:3d} | meta {mes['pesquisa']['meta_ads']:3d} | MQL {mes['pesquisa']['mql']} ({mes['pesquisa']['mql_pct']:.0f}%)")
    print(f"  match:  {mes['match']['matched_pesquisa']}/{mes['match']['vendas_total']} = {mes['match']['match_pct']:.0f}%")
    for s in data['semanas_meta']:
        p = data['periodos'][s['key']]
        print(f"  {s['nome']:9s} ({s['inicio']}-{s['fim']}): "
              f"spend R$ {p['trafego']['spend']:>8,.0f}  "
              f"purch {p['trafego']['purch']:3d}  "
              f"cpa R$ {p['trafego']['cpa']:>7,.0f}  "
              f"hubla {p['hubla']['total']:3d}  "
              f"pesq {p['pesquisa']['meta_ads']:3d} (mql {p['pesquisa']['mql']})")


if __name__ == "__main__":
    main()
