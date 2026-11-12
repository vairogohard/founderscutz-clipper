"""Test de campagnezoeker met nagemaakte pagina's (geen internet nodig)."""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.update(TELEGRAM_BOT_TOKEN="x", TELEGRAM_CHAT_ID="1")
from clipper import campaigns, common, tg  # noqa: E402

def uid(n): return f"{n:08x}-1111-4222-8333-{n:012x}"

def camp(n, title, **kw):
    d = {"id": uid(n), "title": title, "campaignType": "clipping", "status": "active",
         "rewardPerThousandViews": 2.0, "budget": 20000, "budgetSpent": 5000,
         "platforms": ["tiktok", "youtube", "instagram"], "category": {"name": "Podcasts"},
         "requiresApplication": False, "creators": 120,
         "description": "Clip our founder podcast. Every post must include #ad and @acmepod. "
                        "Footage: https://www.youtube.com/@acmepod/videos . No music overlays."}
    d.update(kw)
    return d

# Formaat 1: __NEXT_DATA__
good = camp(1, "Acme Founder Podcast")
board1 = [
    good,
    camp(2, "Lucky Casino Streams"),                                       # gokken
    camp(3, "Daily Crypto Show", category={"name": "Finance"}),            # crypto
    camp(4, "Apply Only Podcast", requiresApplication=True),               # aanvraag
    camp(5, "TikTok Only Show", platforms=["tiktok"]),                     # geen yt/ig
    camp(6, "Nearly Empty Show", budgetSpent=19800),                       # budget op
    camp(7, "Cheap Rate Show", rewardPerThousandViews=0.3),                # laag tarief
    camp(8, "Crowded Show", creators=900),                                 # te veel clippers
    camp(9, "UGC Product Video", campaignType="ugc"),                      # geen clipping
    camp(10, "Nederlandse Podcast Show", description="Knip onze podcast, gebruik #reclame. Alleen Nederlandse "
                                                       "fragmenten zijn toegestaan, dank u wel voor het meedoen é ü ö"),
    camp(11, "Better Business Podcast", rewardPerThousandViews=3.5, budget=50000, budgetSpent=1000, creators=40,
         description="Clip our business podcast. Use #bbp. https://youtube.com/@bizpod"),
]
html1 = ('<html><script id="__NEXT_DATA__" type="application/json">' +
         json.dumps({"props": {"pageProps": {"campaigns": board1}}}) + "</script></html>")

# Formaat 2: Next.js RSC-stukken met andere veldnamen
other = {"campaignId": uid(20), "name": "Growth Interviews", "cpm": 250, "totalBudget": 10000,
         "budgetLeft": 8000, "platforms": [{"platform": "youtube"}, {"platform": "x"}],
         "type": "clipping", "description": "Clip interviews https://youtu.be/abc123 #growth"}
line = "5:" + json.dumps({"data": [other]})
html2 = '<html><script>self.__next_f.push([1,' + json.dumps(line + "\n") + '])</script></html>'

b1 = campaigns.parse_board(html1)
assert len(b1) == len(board1), len(b1)
f = campaigns.settings({})
ranked = campaigns.rank(b1, f)
names = [c["title"] for c in ranked]
print("gekozen volgorde:", names)
assert names == ["Better Business Podcast", "Acme Founder Podcast"], names
top = ranked[0]
assert top["cpm"] == 3.5 and top["budget_left"] == 49000 and top["youtube"] == ["https://youtube.com/@bizpod"]
why = {c["title"]: campaigns.eligible(c, f)[1] for c in b1 if not campaigns.eligible(c, f)[0]}
print("afgevallen:", why)
assert why["Lucky Casino Streams"].startswith("gokken") and why["Apply Only Podcast"] == "aanvraag nodig"
assert why["Nederlandse Podcast Show"] == "niet Engelstalig"

b2 = campaigns.parse_board(html2)
assert len(b2) == 1 and b2[0]["cpm"] == 2.5 and b2[0]["budget_left"] == 8000      # centen-regel
assert b2[0]["platforms"] == ["x", "youtube"] and b2[0]["youtube"] == ["https://youtu.be/abc123"]

# Lege/onbekende pagina geeft een diagnose
bad = "<html><script>self.__next_f.push([1,\"1:{\\\"id\\\":\\\"" + uid(30) + "\\\",\\\"foo\\\":1}\\n\"])</script></html>"
assert campaigns.parse_board(bad) == [] and "mogelijke campagnes" in campaigns.diagnose(bad)

# Tarieven in een lijst per platform (zoals Content Rewards waarschijnlijk doet)
pay = camp(40, "Payout List Podcast", description="Clip our podcast. https://youtube.com/@pl")
for k in ("rewardPerThousandViews",):
    del pay[k]
pay["payouts"] = [{"platform": "tiktok", "rate": 4.0, "minPayout": 10, "maxPayoutPerSubmission": 200},
                  {"platform": "youtube", "rate": 1.8, "minPayout": 10, "maxPayoutPerSubmission": 200},
                  {"platform": "instagram", "rate": 2.2, "minPayout": 10}]
pc = campaigns.parse_board('<script type="application/json">' + json.dumps({"c": [pay]}) + "</script>")[0]
assert pc["cpm"] == 1.8, pc["cpm"]                         # laagste van YouTube en Instagram
assert "gelezen tarief: 1.8" in campaigns.describe_fields(pay) and "payouts" in campaigns.describe_fields(pay)

# --- ensure_campaign ---
sent = []
tg.send_message = lambda t: sent.append(t)
cfg = {**common.load_config(), "gemini_models": []}
state = dict(common.DEFAULT_STATE)
state["sources"] = ["https://studio.youtube.com/channel/UCfoo"]
page = {"html": html1}
campaigns.fetch_html = lambda *a, **k: page["html"]

assert campaigns.ensure_campaign(state, cfg) is True
assert state["campaign"]["title"] == "Better Business Podcast"
assert state["sources"] == ["https://youtube.com/@bizpod"], state["sources"]
assert len(state["campaign_options"]) == 2 and len(sent) == 1
print(sent[0])
assert "/discover/" in sent[0] and "/kies" in sent[0]

assert campaigns.ensure_campaign(state, cfg) is False and len(sent) == 1        # blijft, geen nieuw bericht

# campagne raakt op -> overstap naar de volgende
drained = [dict(d) for d in board1]
drained[10]["budgetSpent"] = 49800
page["html"] = html1.replace(json.dumps({"props": {"pageProps": {"campaigns": board1}}}),
                             json.dumps({"props": {"pageProps": {"campaigns": drained}}}))
assert campaigns.ensure_campaign(state, cfg) is True
assert state["campaign"]["title"] == "Acme Founder Podcast" and any("bijna of helemaal op" in m for m in sent)

# handmatig (auto uit) wordt met rust gelaten, behalve bij /zoek (force)
state["auto_campaign"] = False
before = state["campaign"]["id"]
assert campaigns.ensure_campaign(state, cfg) is False and state["campaign"]["id"] == before
page["html"] = "<html></html>"
n = len(sent)
assert campaigns.ensure_campaign(state, cfg, force=True) is False and len(sent) == n + 1
assert "veranderd" in sent[-1]
# /zoek mag dezelfde campagne weer kiezen als hij de beste blijft
page["html"] = html1
state["auto_campaign"] = True
state["campaign"] = None
campaigns.ensure_campaign(state, cfg)
best = state["campaign"]["id"]
assert campaigns.ensure_campaign(state, cfg, force=True) is True and state["campaign"]["id"] == best
print("alle tests ok")
