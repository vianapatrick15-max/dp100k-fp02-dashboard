# DP100K-Fp02 Dashboard — Status & Retomada

**Live:** https://vianapatrick15-max.github.io/dp100k-fp02-dashboard/
**Repo:** vianapatrick15-max/dp100k-fp02-dashboard (público)
**Última atualização do schema:** 2026-06-03 (v3 — multi-mês)

## TL;DR

Dashboard consolida 3 fontes (Tráfego daily + Hubla + Pesquisa) numa visão única
do **DP100K-Fp02**, com seletor de **MÊS** (Maio/26, Junho/26) e, dentro de cada
mês, seletor de **semana**. Atualiza sozinho hourly via GitHub Action (cron `5 * * * *`).

### Schema v3 (multi-mês) — o que mudou vs v2
- `config.py` define a lista `MESES` (label = prefixo da Turma) + `MES_DEFAULT`.
  As **semanas são auto-descobertas** dos dados (turmas `<label> - N` na aba
  Investimento por Hora) — uma nova `Junho/26 - 3` entra sozinha no refresh, sem editar config.
- `data.json` agora traz `meses_meta` (lista de meses, cada um com `mes_pk` e `semanas[]`
  com `pk`/datas) e `periodos` com **chaves namespaced**: `maio_mes`, `maio_sem1..4`,
  `junho_mes`, `junho_sem1..N`. Há `mes_default` no topo.
- `index.html` tem um grupo de filtro "Mês" (toggle preenchido) antes do "Período".
  `previousKey` compara semana vs semana anterior **do mesmo mês** (não cruza meses).
- KPIs de TODOS os meses vêm da aba **Investimento por Hora** (fonte canônica v2).

## Arquitetura

```
Google Sheets:
  - 1R2MdILmwPZKwBqFpmT5i6VEaiaHYtpwtwCI4F7HLKQo (TRAFEGO daily — IMPORTRANGE de DP100K-Fp Meta Ads)
  - 1G6fjdMB9iwCrnDIHhmSoCC2nbHYIOaEvfRYxPUpBIK8 (CONSOLIDADO TURMA — Hubla, Pesquisa)
       │
       ▼
  fetch_sheets.py ──► analytics.py ──► aggregate.py ──► data.json ──► index.html (fetch + Chart.js)
                                                                          ▲
GitHub Action (cron 5 * * * *) ───────────────────────────────────────────┘
   commits data.json → Pages rebuild auto
```

### Arquivos

| Arquivo | Função |
|---|---|
| [config.py](config.py) | Constantes (sheet IDs, ticket médio, mapping semanas, helpers MQL/parse) |
| [fetch_sheets.py](fetch_sheets.py) | Leitura raw das 3 abas via gspread + Service Account |
| [analytics.py](analytics.py) | Lógica pura: normalize, filter por período, agg KPIs, top ads, persona, MQL por ad, match Hubla×Pesquisa |
| [aggregate.py](aggregate.py) | Orquestra e gera `data.json` |
| [index.html](index.html) | Dashboard estático (Chart.js) com seletor mês/sem1-4 |
| [.github/workflows/refresh.yml](.github/workflows/refresh.yml) | Action hourly que roda aggregate e commita |

## Credenciais e fontes

### Service Account
- **Email:** `ga4-reader@n8n-tathi.iam.gserviceaccount.com` (compartilhada com BWS, Tathi, Andhela)
- **Secret no repo:** `GCP_SA_B64` (JSON base64-encoded — `echo $X | base64 -d > sa.json`)
- **Local:** `/Users/patrickviana/.claude/skills/ga4/credentials/ga4-instituto-andhela.json`

### Planilhas
- **Tráfego** (`1R2MdILmwPZKwBqFpmT5i6VEaiaHYtpwtwCI4F7HLKQo` aba `Página1`): 26 cols, ~3820 linhas (histórico desde set/2025), DP100K Meta Ads daily granular por Ad
- **Consolidado** (`1G6fjdMB9iwCrnDIHhmSoCC2nbHYIOaEvfRYxPUpBIK8`):
  - `Dados_venda_Hubla` — 18 cols, vendas Hubla
  - `Pesquisa` — 37 cols, respondentes (MQL via renda ≥ R$ 8.001)

### Mapping de semanas

| Key | Label (filter na planilha) | Datas |
|---|---|---|
| `sem1` | `Maio/26 - 1` | 2026-04-28 a 2026-05-04 |
| `sem2` | `Maio/26 - 2` | 2026-05-05 a 2026-05-11 |
| `sem3` | `Maio/26 - 3` | 2026-05-12 a 2026-05-18 |
| `sem4` | `Maio/26 - 4` | 2026-05-19 a 2026-05-25 |

## Decisões registradas

- **Filtro Fp02:** linhas de Tráfego e Hubla são filtradas por `Fp02 in nome` pra excluir Fp01 que ainda tem campanha rodando.
- **MQL = renda ≥ R$ 8.001** (regra DP100K, herdada do `refresh_sem3.py`).
- **Match Hubla×Pesquisa por email** lowercase+trim (~74% taxa).
- **ROAS estimado:** usa `TICKET_MEDIO = 1100` em `config.py`. Quando tiver ticket real, substituir lá.
- **Persona dual:** card mostra leads Meta vs compradoras matched — diagnóstico de mismatch.
- **Repo público** (mesma decisão do BWS) — link fixo, sem fricção, risco de expor spend/nomes assumido.

## Snapshot Maio/26 (no dia 2026-05-22)

| Período | Spend | Vendas Hubla | CPA pixel | MQL pesquisa |
|---|---|---|---|---|
| Mês (28/04-25/05) | R$ 67.215 | 266 | R$ 239 | 93/175 = 53% |
| Sem 1 (28/04-04/05) | R$ 17.530 | 62 | R$ 278 | 30/52 |
| Sem 2 (05/05-11/05) | R$ 18.112 | 60 | R$ 274 | 26/50 |
| Sem 3 (12/05-18/05) | R$ 15.254 | 64 | R$ 218 | 22/48 |
| Sem 4 (19/05-25/05) | R$ 16.319 | 80 | R$ 199 | 15/25 |

**Tendência:** CPA caindo (R$ 278 → 199, -28%), vendas subindo (62 → 80, +29%).
Match Hubla×Pesquisa estável ~74%.

## Camadas do dash

1. **Veredito** (5 KPIs) — Spend · Vendas · CPA · ROAS · MQL%
2. **Funil** — Impr → Click → LPV → IC → Compra, com taxa por degrau
3. **Linha do tempo** — spend (barra) + vendas (linha) por dia
4. **Hubla** — 4 cards: vendas, faturamento, % via Meta, match
5. **Top Ads** — tabela performance por anúncio
6. **Persona dual** — distribuição lead vs comprador (idade, renda, ocupação, etc.)
7. **MQL × Ad** — eficiência de qualificação por criativo

## Pra retomar trabalho

### Atualizar manualmente
```bash
cd "/Users/patrickviana/Documents/CLAUDE_CODE_2026/DP100K-Fp02/dashboard"
export GOOGLE_SHEETS_CREDENTIALS_PATH=/Users/patrickviana/.claude/skills/ga4/credentials/ga4-instituto-andhela.json
python3 aggregate.py
python3 -m http.server 8765   # http://localhost:8765
git add data.json && git commit -m "manual refresh" && git push
```

### Trigger workflow manual
```bash
gh workflow run "Refresh DP100K Fp02 Dashboard" --repo vianapatrick15-max/dp100k-fp02-dashboard
```

### Ver logs
```bash
gh run list --workflow="Refresh DP100K Fp02 Dashboard" --repo vianapatrick15-max/dp100k-fp02-dashboard --limit 5
gh run view <run-id> --log --repo vianapatrick15-max/dp100k-fp02-dashboard
```

### Adicionar uma SEMANA nova (mesmo mês)
Nada a fazer — as semanas são **auto-descobertas** das turmas `Junho/26 - N` na aba
Investimento por Hora. Quando o cliente criar a próxima turma, o próximo refresh hourly
já cria o botão `Semana N` e o período `junho_semN`.

### Adicionar um MÊS novo (ex: Julho/26)
Editar `config.py` → lista `MESES`, adicionar `{"key": "julho", "nome": "Julho", "label": "Julho/26"}`
e (opcional) trocar `MES_DEFAULT = "julho"`. As semanas do mês entram sozinhas.
O seletor de mês no `index.html` é montado dinâmico de `meses_meta` — não precisa tocar HTML.

### Mudar ticket médio
`config.py` → `TICKET_MEDIO = 1100.0` → trocar valor.

## Pendências / próximos passos

1. **Persona compradoras** ainda dá 0 quando o período tem poucas matches — adicionar empty state visual mais elegante.
2. **Top ads** mostra duplicados quando mesmo Ad Name roda em 2 adsets (ABO + CBO). Decisão atual: deixar aparecer ambos (cada linha = ad+adset). Se virar ruído, agregar pelo `ad_code`.
3. **CTR baixo** (0.8% no mês) — investigar se é Link CTR (atual) ou All-CTR.
4. **Comparação multi-semana lado-a-lado** — hoje só temos delta vs semana anterior; visão side-by-side seria útil.
5. **Long text VOC** (col 11-14 da pesquisa) — quotes da audiência por origem, fica pra v2.
6. **Cidade/Estado** já no JSON via persona, mas não exposto em card próprio ainda.

## Como o usuário se refere

- "Dashboard DP100K-Fp02"
- "Dash da Fp02"

## Token mapping (referência)

| utm_source bruto | Origem agrupada |
|---|---|
| `meta_ads`, `facebook`, `instagram_ads` | Meta Ads |
| `instagram` | Orgânico Instagram |
| `ipm` | IPM (cross-sell) |
| `whatsapp`, `wpp` | WhatsApp |
| `tathinews`, `activecampaign`, `email` | E-mail |
| vazio / `#N/A` | Sem UTM / Sem origem |
| outros | `Outros (<src>)` |
