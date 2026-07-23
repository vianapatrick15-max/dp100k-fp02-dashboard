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

# --- Consolidada DP100K (Hubla + Investimento por Hora) ---
CONSOLIDADO_SHEET_ID = "1G6fjdMB9iwCrnDIHhmSoCC2nbHYIOaEvfRYxPUpBIK8"
TAB_HUBLA = "Dados_venda_Hubla"
TAB_INVEST = "Investimento por Hora"   # usada só p/ derivar janelas de turma

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


def norm_campanha(s):
    return re.sub(r"\s+", "", (s or "").lower())
