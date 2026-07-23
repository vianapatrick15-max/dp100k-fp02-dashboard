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


def build_all(trafego, hubla_rows, invest_rows, origem_rows, thumbs=None):
    thumbs = thumbs or {}

    # ---- Turmas (janelas) ----
    turmas_all = _turma_windows(invest_rows)
    turmas = [w for w in turmas_all if w["inicio"] >= TURMA_MIN_DATE]

    daily = defaultdict(lambda: {"spend": 0.0, "impr": 0.0, "reach": 0.0, "lclk": 0.0,
                                 "lpv": 0.0, "ic": 0.0, "ing_n": 0, "ing_rev": 0.0,
                                 "ipm_n": 0, "ipm_rev": 0.0, "out_n": 0, "out_rev": 0.0})
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

        ad = g(r, "Ad Name").strip()
        if d >= ADS_SINCE and ad and (spend > 0 or impr > 0):
            ads_daily.append({
                "d": d, "ad": ad, "camp": camp,
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

    # ---- Ingressos (Hubla) — col0 turma, col1 data, col5 oferta, col11 valor ----
    for r in hubla_rows[1:]:
        if len(r) < 12:
            continue
        oferta = (r[5] or "").strip()
        if "dp100k" not in oferta.lower():
            continue
        d = parse_date(r[1])
        if not d:
            continue
        daily[d]["ing_n"] += 1
        daily[d]["ing_rev"] += parse_money(r[11])

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
            "ipm_n": v["ipm_n"], "ipm_rev": round(v["ipm_rev"], 2),
            "out_n": v["out_n"], "out_rev": round(v["out_rev"], 2),
        })

    date_min = dates[0] if dates else None
    date_max = dates[-1] if dates else None
    default_start = default_end = None
    if date_max:
        default_end = date_max
        default_start = date_max[:7] + "-01"   # 1º dia do mês corrente

    return {
        "daily": daily_list,
        "ads_daily": ads_daily,
        "ads_meta": ads_meta,
        "turmas": turmas,
        "meta": {
            "date_min": date_min,
            "date_max": date_max,
            "default_start": default_start,
            "default_end": default_end,
        },
    }
