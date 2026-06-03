"""Orquestrador — gera data.json para o dashboard."""
import json
import os
from datetime import datetime, timezone, timedelta

from fetch_sheets import fetch
from analytics import build_all


def main():
    raw = fetch()
    data = build_all(raw['trafego'], raw['hubla'], raw['pesquisa'], raw['invest'])
    data['updated_at'] = datetime.now(timezone(timedelta(hours=-3))).strftime('%Y-%m-%d %H:%M:%S BRT')
    data['schema_version'] = 3  # v3: multi-mes (Maio+Junho), chaves de periodo namespaced por mes

    out_path = os.path.join(os.path.dirname(__file__), 'data.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    size = os.path.getsize(out_path)
    print(f"data.json: {size:,} bytes")

    # resumo rapido — por mes
    print("\n=== Resumo ===")
    print(f"meses: {[m['key'] for m in data['meses_meta']]}  default={data.get('mes_default')}")
    for m in data['meses_meta']:
        mes = data['periodos'][m['mes_pk']]
        print(f"\n## {m['nome']} ({m.get('inicio','?')} a {m.get('fim','?')}) — todas as turmas")
        print(f"  spend:    R$ {mes['trafego']['spend']:>10,.2f}")
        print(f"  vendas:   gerenc {mes['trafego']['vendas_gerenciador']:3d}  hubla {mes['hubla']['total']:3d}")
        print(f"  CPA:      ger R$ {mes['cpa_gerenciador']:>6,.2f}  hubla R$ {mes['cpa_hubla']:>6,.2f}")
        print(f"  ROAS:     {mes['roas_real']:.2f}x  (fat R$ {mes['hubla']['faturamento']:,.0f})")
        print(f"  CTR:      {mes['trafego']['ctr']:.2f}%  ({mes['trafego']['clicks']} cliques / {mes['trafego']['impressions']:,} impr)")
        print(f"  LPV:      {mes['trafego']['visitas']}  IC: {mes['trafego']['ic']}")
        print(f"  pesq:     total {mes['pesquisa']['total']:3d} | meta {mes['pesquisa']['meta_ads']:3d} | MQL+8k {mes['pesquisa']['mql']} ({mes['pesquisa']['mql_pct']:.1f}%) | MQL+10k {mes['pesquisa']['mql_10k']} ({mes['pesquisa']['mql_10k_pct']:.1f}%)")
        print(f"  match:    {mes['match']['matched_pesquisa']}/{mes['match']['vendas_total']} = {mes['match']['match_pct']:.0f}%")
        for s in m['semanas']:
            p = data['periodos'][s['pk']]
            t = p['trafego']
            print(f"  {s['nome']:9s} ({s.get('inicio','?')}-{s.get('fim','?')}): "
                  f"spend R$ {t['spend']:>8,.0f}  "
                  f"ger {t['vendas_gerenciador']:3d}  "
                  f"hubla {p['hubla']['total']:3d}  "
                  f"CPA-ger R$ {p['cpa_gerenciador']:>5,.0f}  "
                  f"CTR {t['ctr']:.2f}%  "
                  f"LPV {t['visitas']:>4d}  "
                  f"pesq {p['pesquisa']['total']:3d} (mql+8k {p['pesquisa']['mql']})")


if __name__ == "__main__":
    main()
