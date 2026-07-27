"""Config — DP100K Dashboard GERAL (vendas + tráfego, geral e por turma).

Fontes:
  - Tráfego ad-level:   1R2Md... / Página1  (spend, impr, reach, link clicks, LPV, IC, permalink)
  - Ingressos (Hubla):  1G6fj... / Dados_venda_Hubla  (venda real de ingresso)
  - Turmas (janelas):   1G6fj... / Investimento por Hora  (TURMA + DATA)
  - IPM/Outras (backend): 1nIPZ... / [ORIGEM DE VENDAS] - Rafael  (CAMPANHA=DP100K)
"""
import re
from datetime import datetime, timedelta

TICKET_MEDIO = 97.0  # fallback ingresso (não usado — Hubla traz valor real)

# --- Tráfego (ad-level, todas as campanhas DP100K) ---
TRAFEGO_SHEET_ID = "1R2MdILmwPZKwBqFpmT5i6VEaiaHYtpwtwCI4F7HLKQo"
TRAFEGO_TAB = "Página1"

# --- Consolidada DP100K (Hubla + Investimento por Hora + Pesquisa) ---
CONSOLIDADO_SHEET_ID = "1G6fjdMB9iwCrnDIHhmSoCC2nbHYIOaEvfRYxPUpBIK8"
TAB_HUBLA = "Dados_venda_Hubla"
TAB_INVEST = "Investimento por Hora"   # usada só p/ derivar janelas de turma
TAB_PESQUISA = "Pesquisa"              # renda por email (join p/ MQL)

# --- Origem de vendas (backend IPM / outras) — planilha Memorável/Tathi ---
ORIGEM_SHEET_ID = "1nIPZROarNZOtI5p_gdEn4A3brTL7011O7kYfyha84_s"
TAB_ORIGEM = "[ORIGEM DE VENDAS] - Rafael"
ORIGEM_HEADER_ROW = 3       # header real está na 4ª linha (idx 3); dados começam idx 4
ORIGEM_CAMPANHA_DP100K = "dp100k"   # normalizado (sem espaço/lower)

# Turmas exibidas na página "Por turma": de Maio/26 em diante
TURMA_MIN_DATE = "2026-04-27"   # início da Maio/26 - 1

# --- Parsers -----------------------------------------------------------------

def parse_money(s):
    """'R$ 14.997,00' -> 14997.0 ; '97' -> 97.0 ; '120,48' -> 120.48"""
    if s is None:
        return 0.0
    s = str(s).replace("R$", "").strip()
    if not s or s in ("-", "#N/A", "#VALUE!"):
        return 0.0
    s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except Exception:
        return 0.0


def parse_num(s):
    """Número BR genérico (impressões, cliques, CTR...). '1.268'->1268 ; '74,24'->74.24"""
    if s is None:
        return 0.0
    s = str(s).strip()
    if not s or s in ("-", "#N/A", "#VALUE!"):
        return 0.0
    s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except Exception:
        return 0.0


def parse_int(s):
    return int(round(parse_num(s)))


def parse_date(s):
    """Aceita 'DD/MM/YYYY[ HH:MM:SS]', 'YYYY-MM-DD', ISO 'YYYY-MM-DDTHH:MM:SS.sssZ'.
    ISO em UTC é convertido p/ BRT (UTC-3) antes de pegar a data. Retorna 'YYYY-MM-DD' ou None."""
    if not s:
        return None
    s = str(s).strip()
    if not s or s in ("-", "#N/A", "#VALUE!"):
        return None
    # ISO com Z (UTC) -> BRT
    if "T" in s and s.endswith("Z"):
        try:
            base = s[:19]  # YYYY-MM-DDTHH:MM:SS
            dt = datetime.strptime(base, "%Y-%m-%dT%H:%M:%S") - timedelta(hours=3)
            return dt.strftime("%Y-%m-%d")
        except Exception:
            return s[:10]
    s = s.split(" ")[0]
    if "-" in s and len(s) >= 10:
        return s[:10]
    if "/" in s:
        try:
            d, m, y = s.split("/")[:3]
            return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
        except Exception:
            return None
    return None


def safe_div(a, b):
    return (a / b) if b else 0.0


# --- Classificação de FUNIL (oferta_principal / quiz / rmkt / nutricao) -------
# Spec verificado (workflow adversarial 3 lentes + juiz, 2026-07-23):
# precedência rmkt > quiz > nutricao > oferta_principal; token do nome/UTM, nunca
# o número do anúncio (o mesmo AD-NN aparece em funis diferentes). Cobertura de
# spend = 100%. Vendas orgânicas/owned/macros/IPM-backend ficam FORA dos funis pagos.
import re as _re

FUNNELS = ["oferta_principal", "quiz", "rmkt", "nutricao"]
FUNNEL_LABELS = {
    "oferta_principal": "Oferta principal",
    "quiz": "Quiz",
    "rmkt": "RMKT",
    "nutricao": "Nutrição",
}
_RE_RMKT = _re.compile(r"\brmkt\b|\brkmt\b|remarket", _re.I)
_RE_QUIZ = _re.compile(r"\bquiz", _re.I)
_RE_NUTRI = _re.compile(r"\[nt\]|\[vv\]|nutric[aã]o", _re.I)
_RE_VD = _re.compile(r"\[vd\]|\[vendas?\]", _re.I)
_RE_DPAD = _re.compile(r"dp100k-fp0\d", _re.I)
_RE_ISAD = _re.compile(r"\[ad-\d", _re.I)


def classify_funnel(*parts, is_sale=False):
    """Retorna 'oferta_principal'|'quiz'|'rmkt'|'nutricao', ou None (só p/ vendas
    não atribuíveis a funil pago — orgânico/CRM/macro/IPM-backend).
    Tráfego: passar (campaign, adset, ad_name) -> sempre retorna um funil (residual).
    Venda:   passar (utm_content, utm_campaign) com is_sale=True."""
    s = " ".join((p or "") for p in parts).lower()
    if _RE_RMKT.search(s):
        return "rmkt"
    if _RE_QUIZ.search(s):
        return "quiz"
    if _RE_NUTRI.search(s):
        return "nutricao"
    if _RE_VD.search(s):
        return "oferta_principal"
    if is_sale:
        # venda sem token de funil mas de anúncio DP100K identificável -> oferta
        return "oferta_principal" if (_RE_ISAD.search(s) and _RE_DPAD.search(s)) else None
    # tráfego: residual ancorado (toda campanha é dp100k-fp0x) -> oferta
    return "oferta_principal" if _RE_DPAD.search(s) else "oferta_principal"


def is_ipm(produto):
    return "ipm" in (produto or "").lower()


# --- Join venda x criativo: utm_content (Hubla) -> nome do anúncio (Meta) ------
# O utm_content chega deformado pela URL e por renome de ad: '+' no lugar de
# espaço, zero à esquerda ('ad-033' vs 'AD-33'), prefixo 'Teste - ', sufixo de
# funil ausente ('[ad-132][est][vd]' vs '[AD-132][EST][VD][DP100K-Fp02]').
# Igualdade de string crua perdia 229 vendas (todas viravam card fantasma).
_RE_ADPAD = _re.compile(r"ad-?0*(\d+)")
_RE_FUNIL_SUF = _re.compile(r"dp100kfp0\d$")
# venda originada em anúncio de OUTRO funil (IPM/IPL/VPO): o spend dela não está
# neste dashboard, então nunca pode cair no card de um ad DP100K de mesmo número.
_RE_OUTRO_FUNIL = _re.compile(r"\b(ipm|ipl|vpo)-(fp|le)\d", _re.I)


def ad_norm(s):
    s = (s or "").lower().replace("+", " ")
    s = _re.sub(r"^teste\s*-\s*", "", s)
    s = _RE_ADPAD.sub(lambda m: "ad" + str(int(m.group(1))), s)
    return _re.sub(r"[^a-z0-9]+", "", s)


def ad_base(s):
    """Normalizado sem o sufixo de funil (dp100kfp01/dp100kfp02)."""
    return _RE_FUNIL_SUF.sub("", ad_norm(s))


def ad_code(s):
    m = _RE_ADPAD.search((s or "").lower())
    return int(m.group(1)) if m else None


def build_ad_resolver(ad_names, spend_by_ad=None):
    """Devolve resolve(utm_content) -> nome canônico do ad (ou None).

    Escada: exato > normalizado > sem sufixo de funil > código AD-NN.
    O código AD-NN só é usado quando o utm_content NÃO aponta outro funil —
    senão uma venda do [AD-22] do IPM-Fp01 cairia no [AD-22] do DP100K.
    Empate de código resolve pelo ad de maior investimento.
    """
    spend_by_ad = spend_by_ad or {}
    exact, by_norm, by_base, by_code = {}, {}, {}, {}
    for a in ad_names:
        exact.setdefault(a.lower(), a)
        by_norm.setdefault(ad_norm(a), []).append(a)
        by_base.setdefault(ad_base(a), []).append(a)
        c = ad_code(a)
        if c is not None:
            by_code.setdefault(c, []).append(a)

    def pick(cands):
        return max(cands, key=lambda a: spend_by_ad.get(a, 0.0))

    def resolve(utm):
        k = (utm or "").strip().lower()
        if not k:
            return None
        if k in exact:
            return exact[k]
        n = ad_norm(k)
        if n in by_norm:
            return pick(by_norm[n])
        b = ad_base(k)
        if b in by_base:
            return pick(by_base[b])
        if _RE_OUTRO_FUNIL.search(k):
            return None
        c = ad_code(k)
        if c is not None and c in by_code:
            return pick(by_code[c])
        return None

    return resolve


# --- Origem da venda: paga (Meta Ads) vs demais ------------------------------
def is_meta_ads(utm_source):
    return (utm_source or "").strip().lower() in ("meta_ads", "fb", "facebook", "instagram_ads")


# --- MQL: renda mensal >= R$ 10.001 (renda vem da Pesquisa, join por email) ---
_RE_ACIMA = _re.compile(r"acima de r\$\s?([\d.]+)", _re.I)
_RENDA_VAZIA = {"", "#n/a", "#ref!", "#value!", "-"}


def renda_conhecida(renda):
    """True se o comprador respondeu a faixa de renda na pesquisa (qualquer resposta)."""
    return (renda or "").strip().lower() not in _RENDA_VAZIA


def is_mql_renda(renda):
    """MQL = renda mensal >= R$ 10.001. A faixa 8.001-10.000 NÃO conta."""
    s = (renda or "").lower().strip()
    if s in _RENDA_VAZIA:
        return False
    if "r$ 10.001" in s or "r$ 15.001" in s or "r$ 20.001" in s:
        return True
    m = _RE_ACIMA.search(s)
    if m:
        try:
            return float(m.group(1).replace(".", "")) >= 10000
        except Exception:
            return False
    return False


def norm_campanha(s):
    return re.sub(r"\s+", "", (s or "").lower())
