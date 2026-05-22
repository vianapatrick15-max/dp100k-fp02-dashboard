# DP100K-Fp02 — Dashboard

Dashboard de performance do **DP100K — Fp02** (Maio/26).
Consolida três fontes em uma visão única (mês + seletor por semana):

- **Tráfego**: aba `Página1` da planilha `[DP100K-Fp]` (importada via IMPORTRANGE da Meta Ads daily granular)
- **Vendas**: aba `Dados_venda_Hubla` da consolidada `[DP100K-Fp01][CONSOLIDADO][TURMA]`
- **Pesquisa**: aba `Pesquisa` da mesma consolidada (persona + MQL)

**Live:** https://vianapatrick15-max.github.io/dp100k-fp02-dashboard/

## Camadas do dash

1. **Veredito** — 5 KPIs (Spend · Vendas · CPA · ROAS · MQL%) com delta vs semana anterior
2. **Funil** — Impr → Click → LPV → IC → Compra, com taxa em cada degrau
3. **Linha do tempo** — spend (barra) + vendas (linha) por dia
4. **Hubla** — faturamento, ticket médio, % via Meta, match com Pesquisa
5. **Top Ads** — performance por anúncio ordenado por spend
6. **Persona** — distribuição por idade/gênero/renda/ocupação/etc.
   - Dual view: **todos os leads Meta** vs **só compradoras** (matched)
7. **MQL por anúncio** — qual criativo qualifica melhor

## Regras

- **MQL = renda mensal ≥ R$ 8.001** (regra DP100K)
- **Filtro Fp02:** só linhas cuja `Campaign Name` contém `Fp02` (exclui Fp01 ainda rodando)
- **Match Hubla×Pesquisa:** pelo email (lowercase, trim) — typical ~70%
- **ROAS** calculado com ticket médio R$ 1.100 (config.py: `TICKET_MEDIO`)

## Rodar localmente

```bash
export GOOGLE_SHEETS_CREDENTIALS_PATH=/path/to/service-account.json
python3 aggregate.py        # gera data.json
python3 -m http.server 8765 # abre http://localhost:8765
```

## Pipeline

```
Google Sheets (3 abas) ──► fetch_sheets ──► analytics ──► aggregate ──► data.json ──► index.html
                                                                            ▲
GitHub Action (cron 5 * * * *) ─────────────────────────────────────────────┘
   commits data.json → Pages rebuild
```

Veja [STATUS.md](STATUS.md) pra retomar trabalho.
