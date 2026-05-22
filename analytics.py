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
# INVESTIMENTO POR HORA (FONTE CANONICA dos KPIs por turma)
# ============================================================================

def invest_normalize(rows):
    """Normaliza Investimento por Hora. Mantem coluna `turma` pra filtrar.
    Cols esperadas: Turma, CHAVE, DATA, HORA, INVESTIDO, VENDAS, INITIATE CHECKOUT,
                    CTR, VISITAS A PAGINA, IMPRESSOES, CLICKS"""
    out = []
    for r in rows:
        turma = (r.get('Turma') or '').strip()
        if not turma.startswith('Maio/26'):
            continue
        out.append({
            'turma': turma,
            'date': parse_date(r.get('DATA', '')),
            'hora': r.get('HORA', '') or '',
            'spend':   parse_money(r.get('INVESTIDO', 0)),
            'vendas':  parse_int(r.get('VENDAS', 0)),
            'ic':      parse_int(r.get('INITIATE CHECKOUT', 0)),
            'visitas': parse_int(r.get('VISITAS A PAGINA', 0)),
            'impr':    parse_int(r.get('IMPRESSÕES', 0)),
            'clicks':  parse_int(r.get('CLICKS', 0)),
        })
    return out


def filter_invest_turmas(rows, turma_labels):
    return [r for r in rows if r['turma'] in turma_labels]


def date_range_from_invest(rows):
    """Range REAL de datas dadas as linhas filtradas."""
    dates = sorted({r['date'] for r in rows if r['date']})
    return (dates[0], dates[-1]) if dates else (None, None)


def agg_invest(rows):
    if not rows:
        return _empty_invest()
    spend = sum(r['spend'] for r in rows)
    vendas = sum(r['vendas'] for r in rows)
    ic = sum(r['ic'] for r in rows)
    visitas = sum(r['visitas'] for r in rows)
    impr = sum(r['impr'] for r in rows)
    clicks = sum(r['clicks'] for r in rows)
    return {
        'spend': spend,
        'vendas_gerenciador': vendas,
        'ic': ic,
        'visitas': visitas,
        'impressions': impr,
        'clicks': clicks,
        'ctr':   safe_div(clicks, impr) * 100,
        'cpm':   safe_div(spend, impr) * 1000,
        'cpc':   safe_div(spend, clicks),
        'cpa':   safe_div(spend, vendas),
        'cpic':  safe_div(spend, ic),
        'cplpv': safe_div(spend, visitas),
        'click_lpv':  safe_div(visitas, clicks) * 100,
        'lpv_ic':     safe_div(ic, visitas) * 100,
        'ic_purch':   safe_div(vendas, ic) * 100,
        'lpv_purch':  safe_div(vendas, visitas) * 100,
    }


def _empty_invest():
    return {k: 0 for k in ['spend','vendas_gerenciador','ic','visitas','impressions','clicks',
                           'ctr','cpm','cpc','cpa','cpic','cplpv',
                           'click_lpv','lpv_ic','ic_purch','lpv_purch']}


def daily_series_invest(rows):
    """Serie diaria agregada da Invest por Hora."""
    by = defaultdict(lambda: dict(spend=0, vendas=0, ic=0, visitas=0, impr=0, clicks=0))
    for r in rows:
        d = r['date']
        if not d:
            continue
        b = by[d]
        b['spend']   += r['spend']
        b['vendas']  += r['vendas']
        b['ic']      += r['ic']
        b['visitas'] += r['visitas']
        b['impr']    += r['impr']
        b['clicks']  += r['clicks']
    return [dict(date=d, **v) for d, v in sorted(by.items())]


# ============================================================================
# TRAFEGO (daily granular) — usado pra top_ads e persona-por-ad
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
    """Normaliza Hubla SEM filtrar por Fp02 — filtragem real eh por TURMA."""
    out = []
    for r in rows:
        turma = (r.get('Turma') or '').strip()
        out.append({
            'turma':    turma,
            'data':     parse_date(r.get('data', '') or r.get('DATA', '')),
            'email':    (r.get('email') or '').strip().lower(),
            'utm_source':   (r.get('utm source') or '').strip().lower(),
            'utm_content':  (r.get('utm content') or '').strip().lower(),
            'utm_campaign': (r.get('utm campaign') or '').strip().lower(),
            'valor':    parse_money(r.get('valor', 0)),
            'mql_renda': r.get('MQL') or '',
        })
    return out


def filter_hubla_turmas(rows, turma_labels):
    return [r for r in rows if r['turma'] in turma_labels]


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
    """Filtro por data (fallback quando turma nao disponivel)."""
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
        # planilha tem 2 cols 'Turma' (col 0 e col 35). O fetch desambigua com __2.
        # Regra de pertinencia: linha pertence a uma turma se QUALQUER uma das 2 cols bater.
        t0 = (r.get('Turma') or '').strip()
        t1 = (r.get('Turma__2') or '').strip()
        turma = t0 if t0.startswith(('Maio/26','Abril/26','Marco/26','Fevereiro/26','Janeiro/26')) else t1
        out.append({
            'turma':     turma,
            'turmas':    [t for t in (t0, t1) if t],  # ambas cols pra filtro abrangente
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


def filter_pesquisa_turmas(rows, turma_labels):
    """Linha pertence a uma das turmas se QUALQUER uma das suas 2 cols Turma bater."""
    targets = set(turma_labels)
    return [r for r in rows if any(t in targets for t in r.get('turmas', []))]


def filter_pesquisa_period(rows, inicio, fim):
    return [r for r in rows if r['submitted'] and inicio <= r['submitted'] <= fim]


def agg_pesquisa(rows):
    if not rows:
        return _empty_pesquisa()
    total = len(rows)
    meta = [r for r in rows if 'meta' in r['origem'] or 'facebook' in r['origem']]
    mql_meta = [r for r in meta if r['is_mql']]
    mql_total = [r for r in rows if r['is_mql']]
    mql10k_meta = [r for r in meta if _is_mql_10k(r['income'])]
    mql10k_total = [r for r in rows if _is_mql_10k(r['income'])]
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
        'mql_total': len(mql_total),
        'mql_total_pct': safe_div(len(mql_total), total) * 100,
        'mql_10k': len(mql10k_total),
        'mql_10k_pct': safe_div(len(mql10k_total), total) * 100,
        'mql_10k_meta': len(mql10k_meta),
        'mql_10k_meta_pct': safe_div(len(mql10k_meta), len(meta)) * 100,
        'por_origem': [{'origem': o, 'n': n, 'pct': safe_div(n, total) * 100}
                        for o, n in by_origem.most_common()],
    }


def _is_mql_10k(renda):
    """MQL alto: renda >= R$ 10.001."""
    s = (renda or '').lower().strip()
    if 'r$ 10.001' in s or 'r$ 15.001' in s or 'r$ 20.001' in s:
        return True
    if 'acima de r$' in s:
        m = re.search(r'acima de r\$\s?([\d.]+)', s)
        if m:
            try:
                return float(m.group(1).replace('.', '')) >= 10000
            except Exception:
                return False
    return False


def _empty_pesquisa():
    return {'total': 0, 'meta_ads': 0, 'pct_meta': 0, 'mql': 0, 'mql_pct': 0,
            'mql_total': 0, 'mql_total_pct': 0, 'mql_10k': 0, 'mql_10k_pct': 0,
            'mql_10k_meta': 0, 'mql_10k_meta_pct': 0,
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


def persona_por_ad(pesquisa_rows, min_n=3):
    """Persona individual de cada AD (so leads Meta).

    Retorna {AD-XX: persona_blob} para todos ads com >= min_n respondentes.
    """
    by = defaultdict(list)
    for r in pesquisa_rows:
        if 'meta' not in r['origem'] and 'facebook' not in r['origem']:
            continue
        code = ad_code_from(r['content']) or 'unknown'
        by[code].append(r)
    out = {}
    for code, rows in by.items():
        if len(rows) < min_n:
            continue
        out[code] = persona(rows)
    return out


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

def build_periodo(trafego_n, hubla_n, pesquisa_n, invest_n, turma_labels, label, nome):
    """Monta o blob completo de um periodo (turma_labels = lista de Turma strings).

    - KPIs (spend/vendas/IC/visitas/impr/clicks/CTR) vem da aba `Investimento por Hora`
      (FONTE CANONICA do cliente — bate com a apuracao manual).
    - Hubla e Pesquisa: filtragem por TURMA (coluna Turma).
    - Top_ads e persona_por_ad: vem do Trafego daily, filtrado pelo range de datas
      REAIS observado no Invest por Hora pra essas turmas.
    """
    inv = filter_invest_turmas(invest_n, turma_labels)
    ini, fim = date_range_from_invest(inv)
    tr = filter_period(trafego_n, ini, fim) if ini else []
    hb = filter_hubla_turmas(hubla_n, turma_labels)
    pq = filter_pesquisa_turmas(pesquisa_n, turma_labels)

    # persona Meta apenas
    pq_meta = [r for r in pq if 'meta' in r['origem'] or 'facebook' in r['origem']]
    _, _, buyer_pesq = match_buyers(hb, pq)

    inv_kpis = agg_invest(inv)
    hh = agg_hubla(hb)
    # ROAS = faturamento Hubla / spend (canonico do Invest)
    roas_real = safe_div(hh['faturamento'], inv_kpis['spend'])
    # CPA: 2 calculos (Vendas Gerenciador = pixel; Hubla = real)
    cpa_ger = safe_div(inv_kpis['spend'], inv_kpis['vendas_gerenciador'])
    cpa_hubla = safe_div(inv_kpis['spend'], hh['total'])

    return {
        'periodo': {
            'inicio': ini, 'fim': fim,
            'label': label, 'nome': nome,
            'turmas': turma_labels,
        },
        'trafego':  inv_kpis,             # CANONICO (Invest por Hora)
        'hubla':    hh,
        'pesquisa': agg_pesquisa(pq),
        'persona_leads_meta': persona(pq_meta),
        'persona_compradoras_meta': persona_compradoras_meta(buyer_pesq),
        'match':    match_summary(len(hb), buyer_pesq),
        'top_ads':  top_ads(tr, limit=30),
        'mql_por_ad':    mql_por_ad(pq, top_n=20),
        'persona_por_ad': persona_por_ad(pq, min_n=3),
        'serie_diaria':  daily_series_invest(inv),
        'roas_real':     roas_real,
        'cpa_hubla':     cpa_hubla,
        'cpa_gerenciador': cpa_ger,
    }


def export_raw(invest_n, trafego_n, hubla_n, pesquisa_n, date_min=None, date_max=None):
    """Exporta dados granulares em formato compact array-of-arrays pra client-side filter.

    Limita ao range [date_min, date_max] pra controlar tamanho do JSON.

    Schema:
      invest:   [date, spend, vendas, ic, visitas, impr, clicks]
      trafego:  [date, ad_name, ad_code, campaign, adset, spend, impr, clicks, lpv, ic, purch, ad_status, ig_url]
      hubla:    [data, email, utm_source, utm_content, valor]
      pesquisa: [submitted, email, origem, content, age, gender, time, prev, occ, income, self_img, desire, state, is_mql, is_mql_10k]
    """
    def in_range(d):
        if not d: return False
        if date_min and d < date_min: return False
        if date_max and d > date_max: return False
        return True

    # Agregar invest por dia (vem horario) — pra filtro custom ser por dia natural
    by_day = defaultdict(lambda: dict(spend=0.0, vendas=0, ic=0, visitas=0, impr=0, clicks=0))
    for r in invest_n:
        if not in_range(r['date']):
            continue
        b = by_day[r['date']]
        b['spend']   += r['spend']
        b['vendas']  += r['vendas']
        b['ic']      += r['ic']
        b['visitas'] += r['visitas']
        b['impr']    += r['impr']
        b['clicks']  += r['clicks']
    inv = [[d, round(v['spend'], 2), v['vendas'], v['ic'], v['visitas'], v['impr'], v['clicks']]
           for d, v in sorted(by_day.items())]
    tr = [[r['date'], r['ad'], ad_code_from(r['ad']), r['campaign'][:80], r['adset'][:80],
           round(r['spend'], 2), r['impr'], r['clicks'], r['lpv'], r['ic'], r['purch'],
           r['ad_status'], r['ig_url']]
          for r in trafego_n if in_range(r['date'])]
    hb = [[r['data'], r['email'], r['utm_source'], r['utm_content'], round(r['valor'], 2)]
          for r in hubla_n if in_range(r['data'])]
    pq = [[r['submitted'], r['email'], r['origem'], r['content'],
           r['age'], r['gender'], r['time'], r['prev'], r['occ'], r['income'],
           r['self_img'], r['desire'], r['state'], r['is_mql'], _is_mql_10k(r['income'])]
          for r in pesquisa_n if in_range(r['submitted'])]
    return {
        'invest':   {'cols': ['date','spend','vendas','ic','visitas','impr','clicks'], 'rows': inv},
        'trafego':  {'cols': ['date','ad','ad_code','campaign','adset','spend','impr','clicks','lpv','ic','purch','ad_status','ig_url'], 'rows': tr},
        'hubla':    {'cols': ['data','email','utm_source','utm_content','valor'], 'rows': hb},
        'pesquisa': {'cols': ['submitted','email','origem','content','age','gender','time','prev','occ','income','self_img','desire','state','is_mql','is_mql_10k'], 'rows': pq},
    }


def build_all(trafego_raw, hubla_raw, pesquisa_raw, invest_raw):
    """Constroi o data.json completo (mes + 4 semanas)."""
    trafego_n  = trafego_normalize(trafego_raw)
    hubla_n    = hubla_normalize(hubla_raw)
    pesquisa_n = pesquisa_normalize(pesquisa_raw)
    invest_n   = invest_normalize(invest_raw)

    out = {
        'produto': PRODUTO,
        'ticket_medio': TICKET_MEDIO,
        'semanas_meta': [{'key': s['key'], 'nome': s['nome'], 'label': s['label']} for s in SEMANAS],
        'periodos': {},
    }

    # MES (uniao das 4 turmas)
    todas = [s['label'] for s in SEMANAS]
    out['periodos']['mes'] = build_periodo(
        trafego_n, hubla_n, pesquisa_n, invest_n, todas,
        label='Mes Completo', nome='Maio/26 — Mês',
    )
    # cada semana = uma turma
    for s in SEMANAS:
        out['periodos'][s['key']] = build_periodo(
            trafego_n, hubla_n, pesquisa_n, invest_n, [s['label']],
            label=s['label'], nome=s['nome'],
        )
        # injeta range de datas no meta da semana pra UI
        peri = out['periodos'][s['key']]['periodo']
        for sm in out['semanas_meta']:
            if sm['key'] == s['key']:
                sm['inicio'] = peri['inicio']
                sm['fim'] = peri['fim']

    out['_diag'] = {
        'trafego_linhas': len(trafego_n),
        'hubla_linhas': len(hubla_n),
        'pesquisa_linhas': len(pesquisa_n),
        'invest_linhas': len(invest_n),
    }
    # raw pra filtro personalizado client-side — limita ao range visivel (Maio/26)
    inv_dates = sorted({r['date'] for r in invest_n if r['date']})
    date_min = inv_dates[0] if inv_dates else None
    date_max = inv_dates[-1] if inv_dates else None
    out['raw'] = export_raw(invest_n, trafego_n, hubla_n, pesquisa_n, date_min, date_max)
    out['raw']['date_min'] = date_min
    out['raw']['date_max'] = date_max
    return out
