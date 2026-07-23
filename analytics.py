"""Analytics — monta o modelo do dashboard geral DP100K.

Saída (data.json):
  daily     : [{d, spend, impr, reach, lclk, lpv, ic, ing_n, ing_rev,
               ipm_n, ipm_rev, out_n, out_rev}]  — 1 linha por dia (union tráfego+vendas)
  ads_daily : [{d, ad, camp, spend, purch, impr, ic, lpv, lclk}]  — ad×dia (>= 2026-01-01)
  ads_meta  : {ad: {permalink, preview, status, camp, thumb}}
  turmas    : [{label, inicio, fim}]  — Maio/26 em diante
  meta      : {updated_at, date_min, date_max, default_start, default_end}
"""
from collections import defaultdict
from datetime import datetime, timedelta

from config import (
    parse_money, parse_num, parse_date, is_ipm, norm_campanha,
    ORIGEM_HEADER_ROW, ORIGEM_CAMPANHA_DP100K, TURMA_MIN_DATE,
    classify_funnel, FUNNELS, FUNNEL_LABELS,
    is_mql_renda, renda_conhecida,
)

ADS_SINCE = "2026-01-01"


def _turma_windows(invest_rows):
    starts, ends = {}, {}
    for r in invest_rows[1:]:
        if len(r) < 4:
            continue
        t = (r[1] or "").strip()
        d = parse_date(r[3])
        if not t or not d:
            continue
        if t not in starts or d < starts[t]:
            starts[t] = d
        if t not in ends or d > ends[t]:
            ends[t] = d
    seq = sorted(((t, starts[t], ends[t]) for t in starts), key=lambda x: x[1])
    wins = []
    for i, (t, s, e) in enumerate(seq):
        if i + 1 < len(seq):
            nxt = seq[i + 1][1]
            end = (datetime.strptime(nxt, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
            if end < s:
                end = e
        else:
            end = e
        wins.append({"label": t, "inicio": s, "fim": end})
    return wins


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


def build_all(trafego, hubla_rows, invest_rows, origem_rows, pesquisa_rows=None, thumbs=None):
    thumbs = thumbs or {}
    email_renda = _email_renda_map(pesquisa_rows or [])

    # ---- Turmas (janelas) ----
    turmas_all = _turma_windows(invest_rows)
    turmas = [w for w in turmas_all if w["inicio"] >= TURMA_MIN_DATE]

    daily = defaultdict(lambda: {"spend": 0.0, "impr": 0.0, "reach": 0.0, "lclk": 0.0,
                                 "lpv": 0.0, "ic": 0.0, "ing_n": 0, "ing_rev": 0.0,
                                 "ing_renda": 0, "ing_mql": 0,
                                 "ipm_n": 0, "ipm_rev": 0.0, "out_n": 0, "out_rev": 0.0})
    # seg_daily[funil][data] -> tráfego + ingressos atribuídos ao funil pago
    seg_daily = {f: defaultdict(lambda: {"spend": 0.0, "impr": 0.0, "reach": 0.0,
                 "lclk": 0.0, "lpv": 0.0, "ic": 0.0, "ing_n": 0, "ing_rev": 0.0,
                 "ing_renda": 0, "ing_mql": 0})
                 for f in FUNNELS}
    # hubla por ad (utm_content) x dia -> ingressos + renda conhecida + MQL
    hubla_ads = defaultdict(lambda: {"ing": 0, "renda": 0, "mql": 0})
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
            ads_daily.append({
                "d": d, "ad": ad, "camp": camp, "seg": seg,
                "spend": round(spend, 2), "purch": int(purch), "impr": int(impr),
                "ic": int(ic), "lpv": int(lpv), "lclk": int(lclk),
            })
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

    # ---- Ingressos (Hubla) — col1 data, col3 email, col5 oferta, col7 utm_campaign,
    #      col8 utm_content, col11 valor. Renda vem da Pesquisa (join por email) -> MQL>=10k.
    for r in hubla_rows[1:]:
        if len(r) < 12:
            continue
        oferta = (r[5] or "").strip()
        if "dp100k" not in oferta.lower():
            continue
        d = parse_date(r[1])
        if not d:
            continue
        val = parse_money(r[11])
        renda = email_renda.get((r[3] or "").strip().lower(), "")
        has_renda = 1 if renda_conhecida(renda) else 0
        mql = 1 if (has_renda and is_mql_renda(renda)) else 0
        day = daily[d]
        day["ing_n"] += 1
        day["ing_rev"] += val
        day["ing_renda"] += has_renda
        day["ing_mql"] += mql
        utm_content = (r[8] or "").strip()
        seg = classify_funnel(utm_content, r[7], is_sale=True)  # utm_content, utm_campaign
        if seg:
            sd = seg_daily[seg][d]
            sd["ing_n"] += 1
            sd["ing_rev"] += val
            sd["ing_renda"] += has_renda
            sd["ing_mql"] += mql
        k = utm_content.lower()
        if "ad-" in k:
            ha = hubla_ads[(k, d)]
            ha["ing"] += 1
            ha["renda"] += has_renda
            ha["mql"] += mql

    # ---- Backend IPM/Outras (ORIGEM DE VENDAS, CAMPANHA=DP100K) ----
    for r in origem_rows[ORIGEM_HEADER_ROW + 1:]:
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
            })
        seg_out[f] = rows

    # ---- Hubla por ad x dia (p/ % MQL nos ads) ----
    hubla_ads_daily = [
        {"d": d, "k": k, "ing": v["ing"], "renda": v["renda"], "mql": v["mql"]}
        for (k, d), v in hubla_ads.items()
    ]

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
        "meta": {
            "date_min": date_min,
            "date_max": date_max,
            "default_start": default_start,
            "default_end": default_end,
        },
    }
