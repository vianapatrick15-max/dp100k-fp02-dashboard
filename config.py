"""Config — DP100K Fp02 Dashboard."""
from datetime import date

PRODUTO = "DP100K-Fp02"

TICKET_MEDIO = 97.0  # ingresso DP100K (fallback p/ estimativa quando Hubla nao tem valor)

# --- Fontes ---

# Planilha de TRAFEGO (daily granular ads, importada por IMPORTRANGE)
TRAFEGO_SHEET_ID = "1R2MdILmwPZKwBqFpmT5i6VEaiaHYtpwtwCI4F7HLKQo"
TRAFEGO_TAB = "Página1"

# Planilha CONSOLIDADA (Hubla + Pesquisa + Investimento por Hora)
CONSOLIDADO_SHEET_ID = "1G6fjdMB9iwCrnDIHhmSoCC2nbHYIOaEvfRYxPUpBIK8"
TAB_HUBLA = "Dados_venda_Hubla"
TAB_PESQUISA = "Pesquisa"
TAB_INVEST = "Investimento por Hora"   # FONTE CANONICA dos KPIs (spend/vendas/impr/clicks por turma)

# --- Meses ---
# O dashboard cobre multiplos meses. Cada mes tem um label (prefixo da Turma na
# planilha, ex: "Maio/26") e suas semanas sao AUTO-DESCOBERTAS a partir das turmas
# presentes na aba Investimento por Hora (turmas no formato "<label> - N").
# Assim, novas semanas (ex: "Junho/26 - 3") entram sozinhas no refresh hourly,
# sem precisar editar este arquivo.
MESES = [
    {"key": "maio",  "nome": "Maio",  "label": "Maio/26"},
    {"key": "junho", "nome": "Junho", "label": "Junho/26"},
]

# Mes que abre por padrao na UI (mes corrente)
MES_DEFAULT = "junho"

# Prefixos validos de turma (pra filtrar invest/hubla/pesquisa pros meses que exibimos)
MES_LABELS = [m["label"] for m in MESES]

# --- Pesquisa: nomes oficiais das colunas (devem bater com headers da Pesquisa) ---
COL_PESQ_TURMA  = "Turma"
COL_AGE         = "Quantos anos você tem? (multiple-choice)"
COL_GENDER      = "Qual é o seu gênero? (multiple-choice)"
COL_TIME        = "Há quanto tempo você me conhece? (multiple-choice)"
COL_PREV        = "Já participou de algum evento/curso meu antes? (yes-no)"
COL_OCC         = "Qual é sua ocupação atual? (multiple-choice)"
COL_INCOME      = "Qual a sua faixa de renda mensal atual? (multiple-choice)"
COL_SELF        = "Quando se fala em palestras, você se considera: (multiple-choice)"
COL_DESIRE      = "O que você deseja alcançar com o seu conhecimento? (multiple-choice)"
COL_STATE       = "State"
COL_ORIGEM      = "Origem do Lead"
COL_CONTENT     = "Content do Lead"
COL_EMAIL       = "Por fim, qual é o seu e-mail? (email)"

# --- Mapeamento de origens (para agrupar utm_source bruto) ---
ORIGEM_LABELS = {
    "Meta Ads": ["meta", "facebook", "instagram_ads"],
    "Orgânico Instagram": ["instagram"],
    "IPM (cross-sell)": ["ipm"],
    "WhatsApp": ["whatsapp", "wpp"],
    "E-mail": ["tathinews", "activecampaign", "email", "newsletter"],
}


def is_mql_renda(renda):
    """Regra MQL DP100K: renda mensal >= R$ 8.001."""
    import re
    s = (renda or '').lower().strip()
    if 'r$ 8.001' in s or 'r$ 10.001' in s or 'r$ 15.001' in s or 'r$ 20.001' in s:
        return True
    if 'acima de r$' in s:
        m = re.search(r'acima de r\$\s?([\d.]+)', s)
        if m:
            try:
                return float(m.group(1).replace('.', '')) >= 8000
            except Exception:
                return False
    return False


def parse_money(s):
    if not s:
        return 0.0
    s = str(s).replace("R$", "").replace(".", "").replace(",", ".").strip()
    try:
        return float(s)
    except Exception:
        return 0.0


def parse_int(s):
    if not s:
        return 0
    s = str(s).replace(".", "").replace(",", ".").strip()
    try:
        return int(float(s))
    except Exception:
        return 0


def parse_float(s):
    if not s:
        return 0.0
    s = str(s).replace(".", "").replace(",", ".").strip()
    try:
        return float(s)
    except Exception:
        return 0.0


def safe_div(a, b):
    return (a / b) if b else 0


def parse_date(s):
    """Recebe 'YYYY-MM-DD' ou 'DD/MM/YYYY' ou 'DD/MM/YYYY HH:MM:SS', retorna YYYY-MM-DD."""
    if not s:
        return None
    s = s.strip().split(' ')[0]
    if '-' in s and len(s) >= 10:
        return s[:10]
    if '/' in s:
        try:
            d, m, y = s.split('/')[:3]
            return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
        except Exception:
            return None
    return None


def mes_default_key():
    return MES_DEFAULT
