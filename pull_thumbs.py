"""Enriquecimento (rodar local/manual) — puxa thumbnails dos criativos via Meta API
e grava thumbs.json {ad_name: image_url}. O aggregate.py mescla isso nos cards de ads.

Uso:  /usr/bin/python3 pull_thumbs.py
Requer: facebook_business + python-dotenv + token em ~/.claude/skills/meta-ads-memoravel/.env
Não roda no CI (o refresh horário só relê o thumbs.json já commitado).
"""
import os, sys, json, time

from dotenv import load_dotenv
load_dotenv(os.path.expanduser("~/.claude/skills/meta-ads-memoravel/.env"))
from facebook_business.api import FacebookAdsApi
from facebook_business.adobjects.user import User
from facebook_business.adobjects.adaccount import AdAccount

HERE = os.path.dirname(os.path.abspath(__file__))
tok = os.getenv("META_ADS_TOKEN")
app = os.getenv("META_APP_ID")
FacebookAdsApi.init(app_id=app, access_token=tok, api_version="v21.0")

# alvos = ad names usados no dashboard
data = json.load(open(os.path.join(HERE, "data.json"), encoding="utf-8"))
targets = {k.strip(): k for k in data["ads_meta"].keys()}
print(f"alvos: {len(targets)} ad names", file=sys.stderr)

thumbs = {}
try:
    thumbs = json.load(open(os.path.join(HERE, "thumbs.json"), encoding="utf-8"))
except Exception:
    pass

accts = [a.get("account_id") for a in User("me").get_ad_accounts(fields=["account_id"])]
FIELDS = ["name", "creative{thumbnail_url,image_url}"]
FILTER = [{"field": "name", "operator": "CONTAIN", "value": "DP100K"}]

for acc in accts:
    found = seen = 0
    try:
        it = AdAccount(f"act_{acc}").get_ads(
            fields=FIELDS, params={"limit": 50, "filtering": FILTER})
        for ad in it:
            seen += 1
            nm = (ad.get("name") or "").strip()
            if nm not in targets:
                continue
            cr = ad.get("creative") or {}
            url = cr.get("image_url") or cr.get("thumbnail_url")
            if url:
                key = targets[nm]
                if key not in thumbs or not thumbs[key]:
                    thumbs[key] = url
                    found += 1
    except Exception as e:
        print(f"  act_{acc}: ERRO {str(e)[:80]} (vistos {seen})", file=sys.stderr)
        continue
    print(f"  act_{acc}: {seen} ads DP100K, +{found} thumbs (total {sum(1 for v in thumbs.values() if v)})", file=sys.stderr)

with open(os.path.join(HERE, "thumbs.json"), "w", encoding="utf-8") as f:
    json.dump(thumbs, f, ensure_ascii=False, indent=0)
ok = sum(1 for v in thumbs.values() if v)
print(f"\nthumbs.json: {ok}/{len(targets)} com imagem", file=sys.stderr)
