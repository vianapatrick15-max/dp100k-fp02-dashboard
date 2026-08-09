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
  ou período, ordenáveis por vendas / investimento / CPA / **hook** / **hold**.
  Ad de vídeo ganha a faixa **Retenção**: hook rate, hold rate e a curva 25/50/75/100.

### Hook rate e hold rate (ads de vídeo)
| Métrica | Fórmula | O que responde |
|---|---|---|
| **Hook rate** | visualizações de 3s ÷ impressões | quantos pararam o scroll |
| **Hold rate** | 100% assistido ÷ visualizações de 3s | dos que pararam, quantos foram até o fim |
| **Curva** | p25/p50/p75/p100 ÷ visualizações de 3s | **onde** o vídeo perde a audiência |

A curva é o que separa "gancho fraco" de "gancho que promete o que o corpo não entrega":
hook alto com p25 despencando é problema de entrega, não de abertura. Ads estáticos não
têm faixa. Piso de 30 visualizações de 3s — abaixo disso é ruído de placement, não leitura.

**Dimensão Funil** (chips Todos / Oferta principal / Quiz / RMKT / Nutrição — global,
aplica nas 3 views). Classificação verificada (workflow adversarial 3 lentes + juiz):
precedência `rmkt > quiz > nutricao > oferta_principal`, pelo TOKEN do nome/UTM (nunca
pelo número do ad — o mesmo AD-152 tem variante `[vd]` e `[quiz]`). Regex em
`config.classify_funnel`. Cobertura de spend = 100%. No funil, a métrica é tráfego +
ingressos atribuídos via `utm_content`; vendas orgânicas/owned/CRM e IPM/back-end NÃO
entram nos funis pagos — só no Geral (Todos). Nutrição (VV/awareness) tem spend e ~0
venda direta, por isso é bucket próprio (não infla o CPA da oferta).

> **09/08/2026 — nutrição/distribuição entrou no investimento.** A aba `Investimento por
> Hora` (fonte oficial de gasto) filtra objetivo IN (OUTCOME_SALES, CONVERSIONS,
> PRODUCT_CATALOG_SALES), então o gasto de VV/distribuição não estava em lugar nenhum:
> nem no KPI de investimento, nem no CPA, nem no ROAS. Agora `analytics` soma de volta o
> spend do funil `nutricao` vindo do ad-level (`nut_dia`) e só os funis de VENDA são
> reescalados pelo total oficial. Efeito: +R$ 2,3-2,5 mil/mês desde mai/26 (~3% do gasto)
> e CPA blended ~3% maior. O CPA por funil de venda não muda.

## Fontes (lidas pela SA `ga4-reader@n8n-tathi`)
| Dado | Planilha / aba |
|---|---|
| Tráfego ad-level | **Meta Insights API** via `pull_adlevel.py` → `adlevel.json` (2 contas). `1R2Md…` / `Página1` virou só fallback histórico |
| Ingressos (real) | `1G6fj…` / `Dados_venda_Hubla` — **colunas resolvidas pelo header**, não por posição |
| Janelas de turma | `1G6fj…` / `Investimento por Hora` (TURMA + DATA) |
| IPM / outras (backend) | `1nIPZ…` / `[ORIGEM DE VENDAS] - Rafael`, filtrando `CAMPANHA=DP100K` |

IPM = produto contém "IPM"; o resto (MXP/VPO/DZP/II/…) = outras vendas.

> **28/07/2026** — inseriram a coluna `Mes` na frente da aba da Hubla, todos os índices
> deslizaram +1, `oferta` passou a ler telefone e o dashboard ficou ~14h no ar com
> **0 ingressos**. Desde então `analytics._hubla_cols()` resolve as colunas pelo nome do
> header, e `aggregate.py` aborta antes de gravar se der 0 venda com a aba cheia
> (o CI mantém o `data.json` anterior no ar em vez de publicar zero).

## Pipeline
`aggregate.py` → `fetch_sheets.fetch()` (4 abas) → `analytics.build_all()` → `data.json`.
Refresh horário via GitHub Action (`.github/workflows`, cron `5 * * * *`), secret `GCP_SA_B64`.
`data.json` schema v6.

## Enriquecimentos (rodam local, fora do CI)
Os dois geram um JSON que o `aggregate.py` mescla; o refresh horário só relê o arquivo
já commitado. Rodar com `/usr/bin/python3` (o SDK da Meta só está nele) e commitar.

| Script | Gera | Quando rodar |
|---|---|---|
| `pull_adlevel.py` | `adlevel.json` (tráfego por ad × dia + permalink/preview/status) | **toda vez que for atualizar o dash** — sem ele a view Ads, o split por funil e as colunas de volume congelam |
| `pull_thumbs.py` | `thumbs.json` (`ad_name → image_url`) | quando as imagens sumirem — as URLs do CDN da Meta (scontent) expiram em semanas |
| `pull_video.py` | `video.json` (vídeo por ad × dia) | junto do fechamento — sem ele, hook/hold param no último dia puxado |

`pull_adlevel.py` e `pull_video.py` são incrementais: sem argumento repuxam os últimos
dias (a Meta ainda revisa número recente) mais o que faltar; `--full` refaz o histórico
inteiro. Ambos leem as duas contas (C1 Instituto + Memorável). Sem thumb, o card cai no
link "Ver criativo".

> **07/08/2026** — a planilha ad-level do n8n (`Página1`) parou de receber linha em
> 27/07 e ficou 11 dias congelada: KPIs, gráfico, investimento e vendas continuaram
> certos (vêm da aba horária + Hubla), então nada parecia quebrado, mas a view Ads,
> o split por funil e as colunas de volume estavam 11 dias atrás. Além disso a
> planilha só enxergava a conta C1 — a Memorável, que roda o DP100K desde 22/07,
> era invisível. Trocado pela Meta Insights API (`pull_adlevel.py`), conferido contra
> a planilha na janela 20-27/07: spend C1 R$ 16.305,51 nos dois, cliques 2.327 nos
> dois. O `aggregate.py` agora grita no log quando o `adlevel.json` passa de 2 dias
> sem atualizar.
