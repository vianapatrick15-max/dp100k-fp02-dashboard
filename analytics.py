"""Analytics — DP100K Fp02.

Funcoes puras para agregar tres fontes (tráfego diário, Hubla, Pesquisa)
e devolver KPIs / séries / persona / MQL-por-ad por periodo.
"""
import re
from collections import Counter, defaultdict
from datetime import datetime

from config import (
    PRODUTO, TICKET_MEDIO, SEMANAS,
    COL_AGE, COL_GENDER, COL_TIME, COL_PREV, COL_OCC, COL_INCOME,
    COL_SELF, COL_DESIRE, COL_STATE, COL_ORIGEM, COL_CONTENT, COL_EMAIL,
    ORIGEM_LABELS,
    is_mql_renda, parse_money, parse_int, parse_float, parse_date, safe_div,
)


AD_PAT = re.compile(r'AD-(\d+)', re.I)

# ============================================================================
# TRAFEGO (daily granular)
# ============================================================================

def trafego_normalize(rows):
    """Adiciona campos parsed e filtra so Fp02."""
    out = []
    for r in rows:
        camp = r.get('Campaign Name', '') or ''
        if 'Fp02' not in camp:
            continue
        d = {
            'date': parse_date(r.get('Date', '')),
            'campaign': camp,
            'adset': r.get('Adset Name', '') or '',
            'ad': r.get('Ad Name', '') or '',
            'spend': parse_money(r.get('Spend (Cost, Amount Spent)', 0)),
            'purch': parse_int(r.get('Action Omni Purchase', 0)),
            'ic':    parse_int(r.get('Action Omni Initiated Checkout', 0)),
            'impr':  parse_int(r.get('Impressions', 0)),
            'reach': parse_int(r.get('Reach (Estimated)', 0)),
            'freq':  parse_float(r.get('Frequency', 0)),
            'clicks': parse_int(r.get('Action Link Clicks', 0)),
            'ctr':   parse_float(r.get('Inline Link Click CTR', 0)),
            'video_3s': parse_int(r.get('Action 3s Video Views', 0)),
            'lpv':   parse_int(r.get('Action Landing Page View', 0)),
            'roas':  parse_float(r.get('Website Purchase Roas', 0)),
            'camp_status': r.get('Campaign Status', '') or '',
            'ad_status':   r.get('Ad Status', '') or '',
            'ig_url':      r.get('Instagram Permalink URL', '') or '',
        }
        out.append(d)
    return out


def filter_period(rows, inicio, fim):
    return [r for r in rows if r['date'] and inicio <= r['date'] <= fim]


def agg_trafego(rows):
    """Soma KPIs do periodo."""
    if not rows:
        return _empty_trafego()
    spend = sum(r['spend'] for r in rows)
    impr  = sum(r['impr']  for r in rows)
    clicks = sum(r['clicks'] for r in rows)
    lpv   = sum(r['lpv']   for r in rows)
    ic    = sum(r['ic']    for r in rows)
    purch = sum(r['purch'] for r in rows)
    reach = sum(r['reach'] for r in rows)
    fat_estimado = purch * TICKET_MEDIO
    return {
        'spend': spend,
        'impressions': impr,
        'reach': reach,
        'clicks': clicks,
        'lpv': lpv,
        'ic': ic,
        'purch': purch,
        'ctr':   safe_div(clicks, impr) * 100,
        'cpm':   safe_div(spend, impr) * 1000,
        'cpc':   safe_div(spend, clicks),
        'cpa':   safe_div(spend, purch),
        'cpic':  safe_div(spend, ic),
        'cplpv': safe_div(spend, lpv),
        'click_lpv':  safe_div(lpv, clicks) * 100,
        'lpv_ic':     safe_div(ic, lpv) * 100,
        'ic_purch':   safe_div(purch, ic) * 100,
        'lpv_purch':  safe_div(purch, lpv) * 100,
        'roas': safe_div(fat_estimado, spend),
        'faturamento_estimado': fat_estimado,
    }


def _empty_trafego():
    return {k: 0 for k in ['spend','impressions','reach','clicks','lpv','ic','purch',
                           'ctr','cpm','cpc','cpa','cpic','cplpv',
                           'click_lpv','lpv_ic','ic_purch','lpv_purch','roas','faturamento_estimado']}


def daily_series(rows):
    """Serie diaria: [{date, spend, impr, clicks, lpv, ic, purch}]."""
    bydate = defaultdict(lambda: dict(spend=0, impr=0, clicks=0, lpv=0, ic=0, purch=0, reach=0))
    for r in rows:
        d = r['date']
        if not d:
            continue
        b = bydate[d]
        b['spend'] += r['spend']
        b['impr']  += r['impr']
        b['clicks']+= r['clicks']
        b['lpv']   += r['lpv']
        b['ic']    += r['ic']
        b['purch'] += r['purch']
        b['reach'] += r['reach']
    return [dict(date=d, **vals) for d, vals in sorted(bydate.items())]


def ad_code_from(ad_name):
    m = AD_PAT.search(ad_name or '')
    return f"AD-{int(m.group(1)):02d}" if m else None


def top_ads(rows, limit=30):
    """Agrega por Ad Name (consolidando dias). Retorna ordenado por spend desc."""
    byad = defaultdict(lambda: dict(spend=0, impr=0, clicks=0, lpv=0, ic=0, purch=0,
                                     camp_status='', ad_status='', ig_url='', campaign='', adset=''))
    for r in rows:
        k = r['ad']
        if not k:
            continue
        b = byad[k]
        b['spend']  += r['spend']
        b['impr']   += r['impr']
        b['clicks'] += r['clicks']
        b['lpv']    += r['lpv']
        b['ic']     += r['ic']
        b['purch']  += r['purch']
        b['camp_status'] = r['camp_status'] or b['camp_status']
        b['ad_status']   = r['ad_status']   or b['ad_status']
        b['ig_url']      = r['ig_url']      or b['ig_url']
        b['campaign']    = r['campaign']    or b['campaign']
        b['adset']       = r['adset']       or b['adset']
    out = []
    for name, b in byad.items():
        out.append({
            'name': name,
            'ad_code': ad_code_from(name),
            'campaign': b['campaign'],
            'adset': b['adset'],
            'spend': b['spend'],
            'impr':  b['impr'],
            'clicks': b['clicks'],
            'lpv':   b['lpv'],
            'ic':    b['ic'],
            'purch': b['purch'],
            'ctr':   safe_div(b['clicks'], b['impr']) * 100,
            'cpa':   safe_div(b['spend'], b['purch']),
            'cpic':  safe_div(b['spend'], b['ic']),
            'click_lpv':  safe_div(b['lpv'], b['clicks']) * 100,
            'ad_status':   b['ad_status'],
            'camp_status': b['camp_status'],
            'ig_url':      b['ig_url'],
            'roas':        safe_div(b['purch'] * TICKET_MEDIO, b['spend']),
        })
    return sorted(out, key=lambda x: -x['spend'])[:limit]


# ============================================================================
# HUBLA (vendas)
# ============================================================================

def hubla_normalize(rows):
    out = []
    for r in rows:
        produto = (r.get('oferta') or '') + ' ' + (r.get('Campanha') or '') + ' ' + (r.get('utm campaign') or '')
        # so Fp02
        if 'fp02' not in produto.lower():
            continue
        out.append({
            'data':     parse_date(r.get('data', '') or r.get('DATA', '')),
            'email':    (r.get('email') or '').strip().lower(),
            'utm_source':   (r.get('utm source') or '').strip().lower(),
            'utm_content':  (r.get('utm content') or '').strip().lower(),
            'utm_campaign': (r.get('utm campaign') or '').strip().lower(),
            'valor':    parse_money(r.get('valor', 0)),
            'mql_renda': r.get('MQL') or '',
        })
    return out


def origem_group(src):
    s = (src or '').lower().strip()
    if not s:
        return 'Sem UTM'
    for label, keywords in ORIGEM_LABELS.items():
        for kw in keywords:
            if kw in s:
                return label
    if s == 'instagram':
        return 'Orgânico Instagram'
    return f'Outros ({s})'


def filter_hubla_period(rows, inicio, fim):
    return [r for r in rows if r['data'] and inicio <= r['data'] <= fim]


def agg_hubla(rows):
    if not rows:
        return {'total': 0, 'meta_ads': 0, 'pct_meta': 0, 'faturamento': 0, 'ticket_medio': 0,
                'por_origem': []}
    total = len(rows)
    meta = sum(1 for r in rows if 'meta' in r['utm_source'] or 'facebook' in r['utm_source'])
    fat = sum(r['valor'] for r in rows)
    by_origem = Counter(origem_group(r['utm_source']) for r in rows)
    return {
        'total': total,
        'meta_ads': meta,
        'pct_meta': safe_div(meta, total) * 100,
        'faturamento': fat,
        'ticket_medio': safe_div(fat, total),
        'por_origem': [{'origem': o, 'n': n, 'pct': safe_div(n, total) * 100}
                        for o, n in by_origem.most_common()],
    }


# ============================================================================
# PESQUISA
# ============================================================================

def pesquisa_normalize(rows):
    out = []
    for r in rows:
        out.append({
            'turma':     (r.get('Turma') or '').strip(),
            'submitted': parse_date(r.get('Submitted At', '')),
            'email':     (r.get(COL_EMAIL) or '').strip().lower(),
            'origem':    (r.get(COL_ORIGEM) or '').strip().lower(),
            'content':   (r.get(COL_CONTENT) or '').strip(),
            'age':       r.get(COL_AGE) or '',
            'gender':    r.get(COL_GENDER) or '',
            'time':      r.get(COL_TIME) or '',
            'prev':      r.get(COL_PREV) or '',
            'occ':       r.get(COL_OCC) or '',
            'income':    r.get(COL_INCOME) or '',
            'self_img':  r.get(COL_SELF) or '',
            'desire':    r.get(COL_DESIRE) or '',
            'state':     r.get(COL_STATE) or '',
            'is_mql':    is_mql_renda(r.get(COL_INCOME) or ''),
        })
    return out


def filter_pesquisa_period(rows, inicio, fim):
    return [r for r in rows if r['submitted'] and inicio <= r['submitted'] <= fim]


def agg_pesquisa(rows):
    if not rows:
        return _empty_pesquisa()
    total = len(rows)
    meta = [r for r in rows if 'meta' in r['origem'] or 'facebook' in r['origem']]
    mql_meta = [r for r in meta if r['is_mql']]
    by_origem = Counter(
        ('Meta Ads' if ('meta' in r['origem'] or 'facebook' in r['origem'])
         else ('Orgânico Instagram' if r['origem'] == 'instagram'
               else ('IPM (cross-sell)' if r['origem'] == 'ipm'
                     else ('WhatsApp' if r['origem'] in ('whatsapp','wpp')
                           else ('Sem origem' if not r['origem'] or r['origem'] == '#n/a'
                                 else 'Outros')))))
        for r in rows)
    return {
        'total': total,
        'meta_ads': len(meta),
        'pct_meta': safe_div(len(meta), total) * 100,
        'mql': len(mql_meta),
        'mql_pct': safe_div(len(mql_meta), len(meta)) * 100,
        'por_origem': [{'origem': o, 'n': n, 'pct': safe_div(n, total) * 100}
                        for o, n in by_origem.most_common()],
    }


def _empty_pesquisa():
    return {'total': 0, 'meta_ads': 0, 'pct_meta': 0, 'mql': 0, 'mql_pct': 0,
            'por_origem': []}


def dist_col(rows, col_key, top_n=10):
    """Distribuicao de uma coluna (dict key) — exclui vazios."""
    c = Counter((r.get(col_key, '') or '').strip() for r in rows)
    c.pop('', None)
    total = sum(c.values())
    items = c.most_common(top_n) if top_n else c.most_common()
    return [{'k': k, 'n': n, 'pct': safe_div(n, total) * 100} for k, n in items]


def persona(rows):
    """Persona = distribuicao em todas as dimensoes."""
    if not rows:
        return {}
    return {
        'idade':     dist_col(rows, 'age',      8),
        'genero':    dist_col(rows, 'gender',   4),
        'tempo':     dist_col(rows, 'time',     6),
        'previo':    dist_col(rows, 'prev',     3),
        'ocupacao':  dist_col(rows, 'occ',      8),
        'renda':     dist_col(rows, 'income',   8),
        'autoimg':   dist_col(rows, 'self_img', 5),
        'objetivo':  dist_col(rows, 'desire',   6),
        'estado':    dist_col(rows, 'state',   12),
        'total_respondentes': len(rows),
        'mql': sum(1 for r in rows if r.get('is_mql')),
        'mql_pct': safe_div(sum(1 for r in rows if r.get('is_mql')), len(rows)) * 100,
    }


def mql_por_ad(pesquisa_rows, top_n=20):
    """MQL por AD (a partir da coluna content da pesquisa)."""
    by = defaultdict(lambda: dict(total=0, mql=0))
    for r in pesquisa_rows:
        if 'meta' not in r['origem'] and 'facebook' not in r['origem']:
            continue
        code = ad_code_from(r['content'])
        if not code:
            code = 'unknown'
        by[code]['total'] += 1
        if r['is_mql']:
            by[code]['mql'] += 1
    out = [{'ad': k, 'total': v['total'], 'mql': v['mql'],
            'mql_pct': safe_div(v['mql'], v['total']) * 100}
            for k, v in by.items() if v['total'] >= 1]
    return sorted(out, key=lambda x: (-x['mql'], -x['total']))[:top_n]


# ============================================================================
# MATCH Hubla x Pesquisa (compradoras)
# ============================================================================

def match_buyers(hubla_rows, pesquisa_rows):
    """Retorna (email_to_origem, buyer_emails, buyer_pesquisa_rows)."""
    email_to_origem = {}
    for r in hubla_rows:
        em = r['email']
        if not em:
            continue
        og = origem_group(r['utm_source'])
        # se ja existir, prioriza Meta > IPM > outros
        prio = {'Meta Ads': 1, 'IPM (cross-sell)': 2, 'Orgânico Instagram': 3,
                'WhatsApp': 4, 'E-mail': 5, 'Sem UTM': 9}
        if em not in email_to_origem or prio.get(og, 9) < prio.get(email_to_origem[em], 9):
            email_to_origem[em] = og
    buyer_emails = set(email_to_origem.keys())
    buyer_pesq = [r for r in pesquisa_rows if r['email'] in buyer_emails]
    for r in buyer_pesq:
        r['_buyer_origem'] = email_to_origem.get(r['email'])
    return email_to_origem, buyer_emails, buyer_pesq


def match_summary(hubla_total, buyer_pesq):
    return {
        'vendas_total': hubla_total,
        'matched_pesquisa': len(buyer_pesq),
        'match_pct': safe_div(len(buyer_pesq), hubla_total) * 100,
    }


def persona_compradoras_meta(buyer_pesq):
    """Persona das compradoras Meta Ads (que matcharam na pesquisa)."""
    rows = [r for r in buyer_pesq if r.get('_buyer_origem') == 'Meta Ads']
    if not rows:
        return {}
    return persona(rows)


# ============================================================================
# Helpers principais (entry points usados pelo aggregate.py)
# ============================================================================

def build_periodo(trafego_n, hubla_n, pesquisa_n, inicio, fim, label, nome):
    """Monta o blob completo de um periodo."""
    tr = filter_period(trafego_n, inicio, fim)
    hb = filter_hubla_period(hubla_n, inicio, fim)
    pq = filter_pesquisa_period(pesquisa_n, inicio, fim)

    # persona Meta apenas
    pq_meta = [r for r in pq if 'meta' in r['origem'] or 'facebook' in r['origem']]
    _, _, buyer_pesq = match_buyers(hb, pq)

    return {
        'periodo': {
            'inicio': inicio, 'fim': fim,
            'label': label, 'nome': nome,
        },
        'trafego': agg_trafego(tr),
        'hubla':   agg_hubla(hb),
        'pesquisa': agg_pesquisa(pq),
        'persona_leads_meta': persona(pq_meta),
        'persona_compradoras_meta': persona_compradoras_meta(buyer_pesq),
        'match': match_summary(len(hb), buyer_pesq),
        'top_ads': top_ads(tr, limit=30),
        'mql_por_ad': mql_por_ad(pq, top_n=20),
        'serie_diaria': daily_series(tr),
    }


def build_all(trafego_raw, hubla_raw, pesquisa_raw):
    """Constroi o data.json completo (mes + 4 semanas)."""
    trafego_n = trafego_normalize(trafego_raw)
    hubla_n = hubla_normalize(hubla_raw)
    pesquisa_n = pesquisa_normalize(pesquisa_raw)

    out = {
        'produto': PRODUTO,
        'ticket_medio': TICKET_MEDIO,
        'semanas_meta': [{'key': s['key'], 'nome': s['nome'], 'inicio': s['inicio'],
                          'fim': s['fim'], 'label': s['label']} for s in SEMANAS],
        'periodos': {},
    }

    # MES (uniao das 4 semanas)
    out['periodos']['mes'] = build_periodo(
        trafego_n, hubla_n, pesquisa_n,
        SEMANAS[0]['inicio'], SEMANAS[-1]['fim'],
        label='Mes Completo', nome='Maio/26 — Mês',
    )
    # cada semana
    for s in SEMANAS:
        out['periodos'][s['key']] = build_periodo(
            trafego_n, hubla_n, pesquisa_n,
            s['inicio'], s['fim'],
            label=s['label'], nome=s['nome'],
        )

    # diagnostico de saude do dado
    out['_diag'] = {
        'trafego_linhas': len(trafego_n),
        'hubla_linhas': len(hubla_n),
        'pesquisa_linhas': len(pesquisa_n),
    }
    return out
