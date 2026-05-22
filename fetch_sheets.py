"""Fetch DP100K-Fp02 — le 3 fontes brutas.

Output: { trafego: [dicts], hubla: [dicts], pesquisa: [dicts] }
"""
import os
import sys

import gspread
from google.oauth2.service_account import Credentials

from config import (
    TRAFEGO_SHEET_ID, TRAFEGO_TAB,
    CONSOLIDADO_SHEET_ID, TAB_HUBLA, TAB_PESQUISA,
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
        sys.exit(f"Credenciais nao encontradas: {cred_path}")
    creds = Credentials.from_service_account_file(cred_path, scopes=SCOPES)
    return gspread.authorize(creds)


def _read(sheet_id, tab):
    client = _client()
    sh = client.open_by_key(sheet_id)
    ws = sh.worksheet(tab)
    rows = ws.get_all_values()
    if not rows:
        return []
    header = rows[0]
    out = []
    for r in rows[1:]:
        if not any((c or '').strip() for c in r):
            continue
        d = {h: (r[i] if i < len(r) else '') for i, h in enumerate(header)}
        out.append(d)
    return out


def fetch():
    trafego = _read(TRAFEGO_SHEET_ID, TRAFEGO_TAB)
    hubla = _read(CONSOLIDADO_SHEET_ID, TAB_HUBLA)
    pesquisa = _read(CONSOLIDADO_SHEET_ID, TAB_PESQUISA)
    return {"trafego": trafego, "hubla": hubla, "pesquisa": pesquisa}


if __name__ == "__main__":
    d = fetch()
    print(f"trafego  : {len(d['trafego']):5d} linhas")
    print(f"hubla    : {len(d['hubla']):5d} linhas")
    print(f"pesquisa : {len(d['pesquisa']):5d} linhas")
    if d['trafego']:
        print("\ntrafego cols:", list(d['trafego'][0].keys()))
