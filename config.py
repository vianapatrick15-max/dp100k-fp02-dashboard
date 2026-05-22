"""Config — DP100K Fp02 Dashboard."""
from datetime import date

PRODUTO = "DP100K-Fp02"
MES_LABEL = "Maio/26"

TICKET_MEDIO = 1100.0

# --- Fontes ---

# Planilha de TRAFEGO (daily granular ads, importada por IMPORTRANGE)
TRAFEGO_SHEET_ID = "1R2MdILmwPZKwBqFpmT5i6VEaiaHYtpwtwCI4F7HLKQo"
TRAFEGO_TAB = "Página1"

# Planilha CONSOLIDADA (Hubla + Pesquisa)
CONSOLIDADO_SHEET_ID = "1G6fjdMB9iwCrnDIHhmSoCC2nbHYIOaEvfRYxPUpBIK8"
TAB_HUBLA = "Dados_venda_Hubla"
TAB_PESQUISA = "Pesquisa"

# --- Semanas ---
# Cada semana mapeia para um TURMA_LABEL na planilha (col 0 em Hubla e Pesquisa)
# E para um intervalo de datas no Trafego (col Date)
SEMANAS = [
    {"key": "sem1", "label": "Maio/26 - 1", "nome": "Semana 1", "inicio": "2026-04-28", "fim": "2026-05-04"},
    {"key": "sem2", "label": "Maio/26 - 2", "nome": "Semana 2", "inicio": "2026-05-05", "fim": "2026-05-11"},
    {"key": "sem3", "label": "Maio/26 - 3", "nome": "Semana 3", "inicio": "2026-05-12", "fim": "2026-05-18"},
    {"key": "sem4", "label": "Maio/26 - 4", "nome": "Semana 4", "inicio": "2026-05-19", "fim": "2026-05-25"},
]

MES_INICIO = SEMANAS[0]["inicio"]
MES_FIM = SEMANAS[-1]["fim"]

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


def semana_atual_key():
    hoje = date.today().isoformat()
    for s in SEMANAS:
        if s["inicio"] <= hoje <= s["fim"]:
            return s["key"]
    if hoje < SEMANAS[0]["inicio"]:
        return SEMANAS[0]["key"]
    return SEMANAS[-1]["key"]
