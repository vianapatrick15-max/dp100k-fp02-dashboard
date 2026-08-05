"""Analytics — monta o modelo do dashboard geral DP100K.

Saída (data.json):
  daily     : [{d, spend, impr, reach, lclk, lpv, ic, ing_n, ing_rev,
               ipm_n, ipm_rev, out_n, out_rev}]  — 1 linha por dia (union tráfego+vendas)
  ads_daily : [{d, ad, camp, spend, purch, impr, ic, lpv, lclk}]  — ad×dia (>= 2026-01-01)
              + {v3, p25, p50, p75, p100} nos dias em que o ad é vídeo (video.json)
  ads_meta  : {ad: {permalink, preview, status, camp, thumb}}
  turmas    : [{label, inicio, fim}]  — Maio/26 em diante
  meta      : {updated_at, date_min, date_max, default_start, default_end}
"""
from collections import defaultdict
from datetime import datetime, timedelta

from config import (
    parse_money, parse_num, parse_date, parse_dt, is_ipm, norm_campanha,
    ORIGEM_HEADER_ROW, ORIGEM_CAMPANHA_DP100K, TURMA_MIN_DATE,
    classify_funnel, FUNNELS, FUNNEL_LABELS,
    is_mql_renda, renda_conhecida,
    build_ad_resolver, is_meta_ads,
)

ADS_SINCE = "2026-01-01"


def _hourly(invest_rows):
    """[(datetime_da_hora, turma, investido)] da aba 'Investimento por Hora'."""
    out = []
    for r in invest_rows[1:]:
        if len(r) < 6:
            continue
        t = (r[1] or "").strip()
        if not t:
            continue
        dt = parse_dt(f"{parse_date(r[3])} {(r[4] or '00:00').strip()}") if parse_date(r[3]) else None
        if not dt:
            continue
        out.append((dt, t, parse_money(r[5])))
    out.sort(key=lambda x: x[0])
    return out


def _spend_oficial(invest_rows):
    """{data: investido} da aba 'Investimento por Hora' — FONTE OFICIAL de gasto.

    Trocada em 27/07/2026. A planilha de tráfego ad-level (Página1) só exporta a
    conta C1 Instituto (act_1725623984282551); desde 22/07 parte do DP100K roda
    na conta Memorável (act_1835702343244302) e esse gasto ficava invisível
    (Julho/26 - 5: R$ 15.192 no dash vs R$ 18.490 real). A aba horária soma as
    DUAS contas (n8n atualizado 27/07) e é a mesma fonte que o time usa no
    fechamento semanal, então o dash passa a bater com a planilha deles.

    Ressalva conhecida: a coleta horária filtra objetivo IN (OUTCOME_SALES,
    CONVERSIONS, PRODUCT_CATALOG_SALES), então as campanhas de NUTRIÇÃO (VV)
    ficam de fora — ~R$ 500/turma. Validado em 14-19/07: aba horária
    R$ 14.484,36 == ad-level sem nutrição R$ 14.484,34 (Meta API: R$ 14.976,94
    com nutrição). Dias anteriores à cobertura da aba caem no ad-level.
    """
    by_day = defaultdict(float)
    for r in invest_rows[1:]:
        if len(r) < 6:
            continue
        d = parse_date(r[3])
        if not d:
            continue
        by_day[d] += parse_money(r[5])
    return dict(by_day)


def _turma_windows(invest_rows):
    """Janelas de turma com precisão de HORA.

    A virada não é à meia-noite: a aba 'Investimento por Hora' marca a TURMA
    hora a hora e o corte cai no fim da aula (ex: 20/07/2026 às 18:00). Cortar
    por dia jogava o dia inteiro da virada na turma nova — em Julho/26 - 5 isso
    inflava 12 vendas e ~R$ 950 de investimento que eram da turma 4.
    """
    hourly = _hourly(invest_rows)
    starts, ends = {}, {}
    for dt, t, _ in hourly:
        if t not in starts or dt < starts[t]:
            starts[t] = dt
        if t not in ends or dt > ends[t]:
            ends[t] = dt
    seq = sorted(starts, key=lambda t: starts[t])
    wins = []
    for i, t in enumerate(seq):
        ini = starts[t]
        fim = starts[seq[i + 1]] if i + 1 < len(seq) else ends[t] + timedelta(hours=1)
        if fim <= ini:
            fim = ends[t] + timedelta(hours=1)
        wins.append({
            "label": t,
            "inicio": ini.strftime("%Y-%m-%d"),
            "fim": (fim - timedelta(seconds=1)).strftime("%Y-%m-%d"),
            "ini_dt": ini,
            "fim_dt": fim,   # exclusivo
        })
    return wins


def _turma_frac(wins, hourly):
    """frac[label][data] = fatia daquele DIA que pertence à turma (0..1).

    Dia inteiro dentro da janela -> 1.0. Dia de virada -> proporção do
    investimento por hora (a curva real de gasto), com fallback pro número de
    horas quando a aba horária não cobre o dia.
    """
    spend_by_day_turma = defaultdict(float)
    spend_by_day = defaultdict(float)
    for dt, t, v in hourly:
        d = dt.strftime("%Y-%m-%d")
        spend_by_day_turma[(t, d)] += v
        spend_by_day[d] += v

    frac = {w["label"]: {} for w in wins}
    for w in wins:
        lab, ini, fim = w["label"], w["ini_dt"], w["fim_dt"]
        d = datetime.strptime(ini.strftime("%Y-%m-%d"), "%Y-%m-%d")
        last = fim - timedelta(seconds=1)
        while d <= last:
            key = d.strftime("%Y-%m-%d")
            dia_ini, dia_fim = d, d + timedelta(days=1)
            if ini <= dia_ini and fim >= dia_fim:
                frac[lab][key] = 1.0
            else:
                tot = spend_by_day.get(key, 0.0)
                if tot > 0:
                    frac[lab][key] = spend_by_day_turma.get((lab, key), 0.0) / tot
                else:
                    horas = (min(fim, dia_fim) - max(ini, dia_ini)).total_seconds() / 3600.0
                    frac[lab][key] = max(0.0, min(1.0, horas / 24.0))
            d += timedelta(days=1)
    return frac


def _hubla_cols(hubla_rows):
    """Índices das colunas da aba Dados_venda_Hubla, resolvidos pelo HEADER.

    Eram hardcoded por posição até 28/07/2026, quando inseriram a coluna 'Mes' na
    frente: tudo deslizou +1, `oferta` passou a ler telefone, nenhuma linha casava
    com 'dp100k' e o dashboard foi ao ar com 0 ingressos. Resolver por nome evita
    a próxima inserção de coluna.

    A turma fina (ex: 'Julho/26 - 5') está na coluna de header 'x'; a de header
    'Turma' é uma segunda cópia, historicamente desatualizada — só usada se 'x'
    sumir. Levanta ValueError se faltar coluna essencial: melhor quebrar o refresh
    do que publicar zero.
    """
    hdr = [(h or "").strip().lower() for h in (hubla_rows[0] if hubla_rows else [])]

    def find(*alvos, obrigatorio=True):
        for a in alvos:
            if a in hdr:
                return hdr.index(a)
        for a in alvos:                      # 2ª passada: casamento parcial
            for i, h in enumerate(hdr):
                if h and a in h:
                    return i
        if obrigatorio:
            raise ValueError(f"Dados_venda_Hubla: coluna {alvos[0]!r} não encontrada em {hdr}")
        return None

    turma = find("x", obrigatorio=False)
    if turma is None:
        turma = find("turma")
    return {
        "turma": turma,
        "data": find("data"),
        "email": find("email", "e-mail"),
        "oferta": find("oferta"),
        "utm_source": find("utm source", "utm_source"),
        "utm_campaign": find("utm campaign", "utm_campaign"),
        "utm_content": find("utm content", "utm_content"),
        "valor": find("valor"),
    }


def _email_renda_map(pesquisa_rows):
    """Mapa email(lower) -> faixa de renda, a partir da aba Pesquisa."""
    if not pesquisa_rows:
        return {}
    hdr = pesquisa_rows[0]
    ie = ir = None
    for i, h in enumerate(hdr):
        hl = (h or "").lower()
        if ie is None and ("e-mail" in hl or "email" in hl):
            ie = i
        if ir is None and "renda" in hl:
            ir = i
    if ie is None or ir is None:
        return {}
    m = {}
    for r in pesquisa_rows[1:]:
        if len(r) <= max(ie, ir):
            continue
        e = (r[ie] or "").strip().lower()
        rd = (r[ir] or "").strip()
        if e and rd and e not in m:
            m[e] = rd
    return m


def _origem_header_row(rows):
    """Acha a linha de header da aba ORIGEM DE VENDAS pelo conteúdo.

    A aba já teve o header na 4ª linha (idx 3, versão '- Rafael') e hoje tem na 1ª.
    Índices de coluna seguem os mesmos (DATA=0, PRODUTO=1, VALOR=2, CAMPANHA=7);
    só a altura do header muda. Fallback: ORIGEM_HEADER_ROW.
    """
    for i, r in enumerate(rows[:12]):
        if len(r) > 7 and "campanha" in (r[7] or "").strip().lower() \
                and "produto" in (r[1] or "").strip().lower():
            return i
    return ORIGEM_HEADER_ROW


def build_all(trafego, hubla_rows, invest_rows, origem_rows, pesquisa_rows=None,
              thumbs=None, video=None):
    thumbs = thumbs or {}
    video = video or {}
    email_renda = _email_renda_map(pesquisa_rows or [])

    # ---- Turmas (janelas) ----
    turmas_all = _turma_windows(invest_rows)
    turmas = [w for w in turmas_all if w["inicio"] >= TURMA_MIN_DATE]

    daily = defaultdict(lambda: {"spend": 0.0, "impr": 0.0, "reach": 0.0, "lclk": 0.0,
                                 "lpv": 0.0, "ic": 0.0, "ing_n": 0, "ing_rev": 0.0,
                                 "ing_renda": 0, "ing_mql": 0,
                                 "ing_meta": 0, "ing_meta_rev": 0.0,
                                 "ipm_n": 0, "ipm_rev": 0.0, "out_n": 0, "out_rev": 0.0})
    # seg_daily[funil][data] -> tráfego + ingressos atribuídos ao funil pago
    seg_daily = {f: defaultdict(lambda: {"spend": 0.0, "impr": 0.0, "reach": 0.0,
                 "lclk": 0.0, "lpv": 0.0, "ic": 0.0, "ing_n": 0, "ing_rev": 0.0,
                 "ing_renda": 0, "ing_mql": 0, "ing_meta": 0, "ing_meta_rev": 0.0})
                 for f in FUNNELS}
    # hubla por ad (utm_content) x dia -> ingressos + renda conhecida + MQL
    hubla_ads = defaultdict(lambda: {"ing": 0, "renda": 0, "mql": 0})
    vendas = []   # cada ingresso com timestamp, p/ escopo de turma com hora exata
    ads_daily = []
    ads_meta = {}

    def g(row, *names):
        for n in names:
            if n in row:
                return row[n]
        return ""

    # ---- Tráfego (Página1, ad-level, todas campanhas DP100K) ----
    for r in trafego:
        camp = g(r, "Campaign Name")
        if "dp100k" not in camp.lower():
            continue
        d = parse_date(g(r, "Date"))
        if not d:
            continue
        adset = g(r, "Adset Name")
        ad = g(r, "Ad Name").strip()
        spend = parse_money(g(r, "Spend (Cost, Amount Spent)"))
        impr = parse_num(g(r, "Impressions"))
        reach = parse_num(g(r, "Reach (Estimated)"))
        lclk = parse_num(g(r, "Action Link Clicks"))
        lpv = parse_num(g(r, "Action Landing Page View"))
        ic = parse_num(g(r, "Action Omni Initiated Checkout"))
        purch = parse_num(g(r, "Action Omni Purchase"))

        day = daily[d]
        day["spend"] += spend
        day["impr"] += impr
        day["reach"] += reach
        day["lclk"] += lclk
        day["lpv"] += lpv
        day["ic"] += ic

        seg = classify_funnel(camp, adset, ad)  # tráfego: sempre um funil
        sd = seg_daily[seg][d]
        sd["spend"] += spend
        sd["impr"] += impr
        sd["reach"] += reach
        sd["lclk"] += lclk
        sd["lpv"] += lpv
        sd["ic"] += ic

        if d >= ADS_SINCE and ad and (spend > 0 or impr > 0):
            row = {
                "d": d, "ad": ad, "camp": camp, "seg": seg,
                "spend": round(spend, 2), "purch": int(purch), "impr": int(impr),
                "ic": int(ic), "lpv": int(lpv), "lclk": int(lclk),
            }
            # Métricas de vídeo (video.json, puxadas por pull_video.py). Só entram
            # nos dias em que o ad é vídeo — estático não gera chave nenhuma, pra
            # não inflar o data.json com zeros.
            vv = (video.get(ad) or {}).get(d)
            if vv:
                row["v3"], row["p25"], row["p50"], row["p75"], row["p100"] = (
                    int(vv[0]), int(vv[1]), int(vv[2]), int(vv[3]), int(vv[4]))
            ads_daily.append(row)
            m = ads_meta.get(ad)
            if not m or d >= m.get("_last", ""):
                ads_meta[ad] = {
                    "_last": d,
                    "camp": camp,
                    "permalink": g(r, "Instagram Permalink URL").strip(),
                    "preview": g(r, "Preview Shareable Link").strip(),
                    "status": g(r, "Ad Status").strip(),
                    "thumb": thumbs.get(ad, ""),
                }

    for m in ads_meta.values():
        m.pop("_last", None)

    # ---- Investimento oficial: aba 'Investimento por Hora' (2 contas) --------
    # Substitui o spend ad-level (1 conta só) nos dias cobertos pela aba. Os
    # funis são reescalados pela participação ad-level do dia, pra somarem o
    # total oficial. `ads_daily` fica com o spend ad-level cru de propósito: o
    # ranking de criativo tem que continuar sendo gasto real por anúncio, não
    # rateio. Ver docstring de _spend_oficial().
    spend_dia = _spend_oficial(invest_rows)
    for d, oficial in spend_dia.items():
        antigo = daily[d]["spend"]
        daily[d]["spend"] = oficial
        if antigo > 0:
            k = oficial / antigo
            for f in FUNNELS:
                if d in seg_daily[f]:
                    seg_daily[f][d]["spend"] *= k
        elif oficial > 0:
            seg_daily["oferta_principal"][d]["spend"] = oficial

    # Resolver de utm_content -> nome canônico do ad (empate resolve por spend)
    spend_by_ad = defaultdict(float)
    for r in ads_daily:
        spend_by_ad[r["ad"]] += r["spend"]
    resolve_ad = build_ad_resolver(ads_meta.keys(), spend_by_ad)

    # ---- Ingressos (Hubla) — colunas resolvidas pelo header (ver _hubla_cols).
    #      Renda vem da Pesquisa (join por email) -> MQL >= R$ 10.001.
    C = _hubla_cols(hubla_rows)
    largura = max(C.values()) + 1
    for r in hubla_rows[1:]:
        if len(r) < largura:
            continue
        oferta = (r[C["oferta"]] or "").strip()
        if "dp100k" not in oferta.lower():
            continue
        d = parse_date(r[C["data"]])
        if not d:
            continue
        val = parse_money(r[C["valor"]])
        renda = email_renda.get((r[C["email"]] or "").strip().lower(), "")
        has_renda = 1 if renda_conhecida(renda) else 0
        mql = 1 if (has_renda and is_mql_renda(renda)) else 0
        meta = 1 if is_meta_ads(r[C["utm_source"]]) else 0
        day = daily[d]
        day["ing_n"] += 1
        day["ing_rev"] += val
        day["ing_renda"] += has_renda
        day["ing_mql"] += mql
        day["ing_meta"] += meta
        day["ing_meta_rev"] += val if meta else 0.0
        utm_content = (r[C["utm_content"]] or "").strip()
        seg = classify_funnel(utm_content, r[C["utm_campaign"]], is_sale=True)
        if seg:
            sd = seg_daily[seg][d]
            sd["ing_n"] += 1
            sd["ing_rev"] += val
            sd["ing_renda"] += has_renda
            sd["ing_mql"] += mql
            sd["ing_meta"] += meta
            sd["ing_meta_rev"] += val if meta else 0.0
        vendas.append({"dt": parse_dt(r[C["data"]]) or datetime.strptime(d, "%Y-%m-%d"), "d": d,
                       "turma": (r[C["turma"]] or "").strip(),
                       "seg": seg, "val": val, "renda": has_renda, "mql": mql, "meta": meta})
        k = utm_content.lower()
        if "ad-" in k:
            canon = resolve_ad(utm_content)
            ha = hubla_ads[(canon.lower() if canon else k, d)]
            ha["ing"] += 1
            ha["renda"] += has_renda
            ha["mql"] += mql

    # ---- Backend IPM/Outras (ORIGEM DE VENDAS, CAMPANHA=DP100K) ----
    for r in origem_rows[_origem_header_row(origem_rows) + 1:]:
        if len(r) < 8:
            continue
        d = parse_date(r[0])
        if not d:
            continue
        if ORIGEM_CAMPANHA_DP100K not in norm_campanha(r[7]):
            continue
        val = parse_money(r[2])
        if is_ipm(r[1]):
            daily[d]["ipm_n"] += 1
            daily[d]["ipm_rev"] += val
        else:
            daily[d]["out_n"] += 1
            daily[d]["out_rev"] += val

    # ---- Serializa daily ----
    dates = sorted(daily.keys())
    daily_list = []
    for d in dates:
        v = daily[d]
        daily_list.append({
            "d": d,
            "spend": round(v["spend"], 2), "impr": int(v["impr"]), "reach": int(v["reach"]),
            "lclk": int(v["lclk"]), "lpv": int(v["lpv"]), "ic": int(v["ic"]),
            "ing_n": v["ing_n"], "ing_rev": round(v["ing_rev"], 2),
            "ing_renda": v["ing_renda"], "ing_mql": v["ing_mql"],
            "ing_meta": v["ing_meta"], "ing_meta_rev": round(v["ing_meta_rev"], 2),
            "ipm_n": v["ipm_n"], "ipm_rev": round(v["ipm_rev"], 2),
            "out_n": v["out_n"], "out_rev": round(v["out_rev"], 2),
        })

    # ---- Serializa seg_daily (por funil) ----
    seg_out = {}
    for f in FUNNELS:
        rows = []
        for d in sorted(seg_daily[f].keys()):
            v = seg_daily[f][d]
            rows.append({
                "d": d, "spend": round(v["spend"], 2), "impr": int(v["impr"]),
                "reach": int(v["reach"]), "lclk": int(v["lclk"]), "lpv": int(v["lpv"]),
                "ic": int(v["ic"]), "ing_n": v["ing_n"], "ing_rev": round(v["ing_rev"], 2),
                "ing_renda": v["ing_renda"], "ing_mql": v["ing_mql"],
                "ing_meta": v["ing_meta"], "ing_meta_rev": round(v["ing_meta_rev"], 2),
            })
        seg_out[f] = rows

    # ---- Hubla por ad x dia (p/ % MQL nos ads) ----
    hubla_ads_daily = [
        {"d": d, "k": k, "ing": v["ing"], "renda": v["renda"], "mql": v["mql"]}
        for (k, d), v in hubla_ads.items()
    ]

    # ---- Escopo por turma (virada por HORA) --------------------------------
    # Tráfego é diário: no dia da virada rateia pela curva de investimento por
    # hora. Venda tem timestamp: vai pra turma exata, sem rateio.
    frac = _turma_frac(turmas_all, _hourly(invest_rows))
    daily_by_d = {x["d"]: x for x in daily_list}
    seg_by_d = {f: {x["d"]: x for x in seg_out[f]} for f in FUNNELS}
    TRAF = ("spend", "impr", "reach", "lclk", "lpv", "ic")
    ING = ("ing_n", "ing_rev", "ing_renda", "ing_mql", "ing_meta", "ing_meta_rev")

    def _blank(d):
        z = {"d": d}
        z.update({k: 0 for k in TRAF})
        z.update({k: 0 for k in ING})
        return z

    # A venda vai pra turma que a PRÓPRIA planilha marcou (col0 da Hubla, 99,6%
    # preenchida) — é o corte real do carrinho, mais fino que a hora cheia.
    # Sem rótulo, cai no timestamp contra a janela horária.
    labels_conhecidos = {w["label"] for w in turmas_all}

    turma_daily, turma_seg = {}, {}
    for w in turmas:
        lab, f_lab = w["label"], frac.get(w["label"], {})
        v_by_d = defaultdict(lambda: dict.fromkeys(ING, 0))
        vseg_by_d = {f: defaultdict(lambda: dict.fromkeys(ING, 0)) for f in FUNNELS}
        for v in vendas:
            if v["turma"] in labels_conhecidos:
                if v["turma"] != lab:
                    continue
            elif not (w["ini_dt"] <= v["dt"] < w["fim_dt"]):
                continue
            for tgt in (v_by_d[v["d"]],) + ((vseg_by_d[v["seg"]][v["d"]],) if v["seg"] else ()):
                tgt["ing_n"] += 1
                tgt["ing_rev"] += v["val"]
                tgt["ing_renda"] += v["renda"]
                tgt["ing_mql"] += v["mql"]
                tgt["ing_meta"] += v["meta"]
                tgt["ing_meta_rev"] += v["val"] if v["meta"] else 0.0
        rows, srows = [], {f: [] for f in FUNNELS}
        # dias da turma = dias com investimento + dias com venda rotulada nela
        for d in sorted(set(f_lab) | set(v_by_d)):
            fr = f_lab.get(d, 0.0)
            base, row = daily_by_d.get(d), _blank(d)
            if base:
                for k in TRAF:
                    row[k] = round(base[k] * fr, 2) if k == "spend" else int(round(base[k] * fr))
            row.update(v_by_d.get(d, {}))
            # IPM/outras só têm data (sem hora): ficam com a turma dona do meio-dia
            meio = datetime.strptime(d, "%Y-%m-%d") + timedelta(hours=12)
            dono = w["ini_dt"] <= meio < w["fim_dt"]
            for k in ("ipm_n", "ipm_rev", "out_n", "out_rev"):
                row[k] = (base or {}).get(k, 0) if (base and dono) else 0
            rows.append(row)
            for f in FUNNELS:
                sb, srow = seg_by_d[f].get(d), _blank(d)
                if sb:
                    for k in TRAF:
                        srow[k] = round(sb[k] * fr, 2) if k == "spend" else int(round(sb[k] * fr))
                srow.update(vseg_by_d[f].get(d, {}))
                srows[f].append(srow)
        turma_daily[lab] = rows
        turma_seg[lab] = srows

    for w in turmas_all:
        w.pop("ini_dt", None)
        w.pop("fim_dt", None)

    date_min = dates[0] if dates else None
    date_max = dates[-1] if dates else None
    default_start = default_end = None
    if date_max:
        default_end = date_max
        default_start = date_max[:7] + "-01"   # 1º dia do mês corrente

    return {
        "daily": daily_list,
        "seg_daily": seg_out,
        "funnels": [{"key": f, "label": FUNNEL_LABELS[f]} for f in FUNNELS],
        "ads_daily": ads_daily,
        "hubla_ads_daily": hubla_ads_daily,
        "ads_meta": ads_meta,
        "turmas": turmas,
        "turma_daily": turma_daily,
        "turma_seg_daily": turma_seg,
        "meta": {
            "date_min": date_min,
            "date_max": date_max,
            "default_start": default_start,
            "default_end": default_end,
        },
    }
