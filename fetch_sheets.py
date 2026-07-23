"""Fetch — lê as 4 fontes brutas do dashboard geral DP100K.

Retorna:
  trafego     : list[dict]  (Página1, header linha 0, headers únicos)
  hubla_rows  : list[list]  (Dados_venda_Hubla, cru c/ header em [0])
  invest_rows : list[list]  (Investimento por Hora, cru)
  origem_rows : list[list]  (ORIGEM DE VENDAS, cru; header real em idx 3)
"""
import os
import sys

import gspread
from google.oauth2.service_account import Credentials

from config import (
    TRAFEGO_SHEET_ID, TRAFEGO_TAB,
    CONSOLIDADO_SHEET_ID, TAB_HUBLA, TAB_INVEST, TAB_PESQUISA,
    ORIGEM_SHEET_ID, TAB_ORIGEM,
)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]


def _client():
    cred_path = os.environ.get("GOOGLE_SHEETS_CREDENTIALS_PATH")
    if not cred_path:
        env_path = os.path.expanduser("~/.claude/skills/google-sheets/.env")
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    if line.startswith("GOOGLE_SHEETS_CREDENTIALS_PATH="):
                        cred_path = line.split("=", 1)[1].strip().strip('"').strip("'")
                        break
    if not cred_path or not os.path.exists(cred_path):
        sys.exit(f"Credenciais não encontradas: {cred_path}")
    creds = Credentials.from_service_account_file(cred_path, scopes=SCOPES)
    return gspread.authorize(creds)


def _rows(client, sheet_id, tab):
    return client.open_by_key(sheet_id).worksheet(tab).get_all_values()


def _dicts(rows):
    if not rows:
        return []
    header = rows[0]
    seen, hdr = {}, []
    for h in header:
        h = h or ""
        if h in seen:
            seen[h] += 1
            hdr.append(f"{h}__{seen[h]}")
        else:
            seen[h] = 1
            hdr.append(h)
    out = []
    for r in rows[1:]:
        if not any((c or "").strip() for c in r):
            continue
        out.append({h: (r[i] if i < len(r) else "") for i, h in enumerate(hdr)})
    return out


def fetch():
    c = _client()
    trafego_rows = _rows(c, TRAFEGO_SHEET_ID, TRAFEGO_TAB)
    hubla_rows = _rows(c, CONSOLIDADO_SHEET_ID, TAB_HUBLA)
    invest_rows = _rows(c, CONSOLIDADO_SHEET_ID, TAB_INVEST)
    pesquisa_rows = _rows(c, CONSOLIDADO_SHEET_ID, TAB_PESQUISA)
    origem_rows = _rows(c, ORIGEM_SHEET_ID, TAB_ORIGEM)
    return {
        "trafego": _dicts(trafego_rows),
        "hubla_rows": hubla_rows,
        "invest_rows": invest_rows,
        "pesquisa_rows": pesquisa_rows,
        "origem_rows": origem_rows,
    }


if __name__ == "__main__":
    d = fetch()
    print(f"trafego : {len(d['trafego']):5d} linhas")
    print(f"hubla   : {len(d['hubla_rows']):5d} linhas")
    print(f"invest  : {len(d['invest_rows']):5d} linhas")
    print(f"origem  : {len(d['origem_rows']):5d} linhas")
