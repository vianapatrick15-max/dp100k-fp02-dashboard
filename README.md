# DP100K — Dashboard Geral

Dashboard geral de **vendas e tráfego** do DP100K. Consolida ingressos (Hubla),
back-end IPM/outras (origem de vendas) e tráfego ad-level (Meta) num só painel,
com filtro de data livre e visão por turma.

**Live:** https://vianapatrick15-max.github.io/dp100k-fp02-dashboard/

## Views
- **Geral** — período livre (default: mês corrente). 3 dobras:
  1. KPIs: Investimento · Vendas Ingressos · Vendas IPM · Outras Vendas · Faturamento · ROAS
  2. Gráfico de linha por dia: ingressos, IPM, outras (contagem) + faturamento (R$)
  3. Tabela de tráfego por dia: investimento, vendas, impressões, CPM, alcance,
     cliques link, CTR link, visitas página, checkout, conv. página, conv. checkout
- **Por turma** — as mesmas 3 dobras, escopadas por turma (Maio/26 em diante).
- **Ads** — anúncios de melhor desempenho (preview + métricas), filtráveis por turma
  ou período, ordenáveis por vendas / investimento / CPA.

## Fontes (lidas pela SA `ga4-reader@n8n-tathi`)
| Dado | Planilha / aba |
|---|---|
| Tráfego ad-level | `1R2Md…` / `Página1` (spend, impr, alcance, link clicks, LPV, IC, permalink) |
| Ingressos (real) | `1G6fj…` / `Dados_venda_Hubla` (data col1, turma col0, valor col11) |
| Janelas de turma | `1G6fj…` / `Investimento por Hora` (TURMA + DATA) |
| IPM / outras (backend) | `1nIPZ…` / `[ORIGEM DE VENDAS] - Rafael`, filtrando `CAMPANHA=DP100K` |

IPM = produto contém "IPM"; o resto (MXP/VPO/DZP/II/…) = outras vendas.

## Pipeline
`aggregate.py` → `fetch_sheets.fetch()` (4 abas) → `analytics.build_all()` → `data.json`.
Refresh horário via GitHub Action (`.github/workflows`, cron `5 * * * *`), secret `GCP_SA_B64`.
`data.json` schema v4.

Thumbnails dos ads: `thumbs.json` (mapa `ad_name → image_url`, opcional) é mesclado
no aggregate. Sem thumb, o card cai no link "Ver criativo" (Instagram/Preview).
