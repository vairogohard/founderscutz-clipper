#!/usr/bin/env python3
"""Eenmalige installatie: zet de repo op GitHub, slaat je sleutels veilig op als GitHub-secrets,
koppelt Telegram en Buffer en zet de automatische rondes aan. Draai via: bash setup.sh"""
import json
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPO_NAME = "founderscutz-clipper"


def say(text=""):
    print(text, flush=True)


def step(n, text):
    say(f"\n=== Stap {n}: {text} ===")


def ask(prompt, required=True):
    while True:
        value = input(prompt + " ").strip()
        if value or not required:
            return value
        say("Dit veld is verplicht.")


def run(cmd, check=True, capture=False, cwd=ROOT):
    r = subprocess.run(cmd, cwd=cwd, text=True, capture_output=capture)
    if check and r.returncode != 0:
        if capture:
            say(r.stdout + r.stderr)
        raise SystemExit(f"Opdracht mislukt: {' '.join(cmd)}")
    return r


def http_json(url, data=None, headers=None):
    body = None
    headers = dict(headers or {})
    if data is not None:
        body = json.dumps(data).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode())
        except Exception:  # noqa: BLE001
            return {"ok": False, "description": f"HTTP {e.code}", "errors": [{"message": f"HTTP {e.code}"}]}


def telegram(token, method, **params):
    return http_json(f"https://api.telegram.org/bot{token}/{method}?" + urllib.parse.urlencode(params))


def buffer_gql(key, query):
    return http_json("https://api.buffer.com", {"query": query}, {"Authorization": f"Bearer {key}"})


def main():
    say("Installatie van de Founders Cutz clipper. Dit duurt ongeveer 5 minuten.")

    step(1, "Inloggen bij GitHub")
    if run(["gh", "auth", "status"], check=False, capture=True).returncode != 0:
        say("Er opent zo een browservenster. Log in en keur de toegang goed.")
        run(["gh", "auth", "login", "--web", "--git-protocol", "https", "--scopes", "workflow"])
    else:
        run(["gh", "auth", "refresh", "--scopes", "workflow"], check=False)
    run(["gh", "auth", "setup-git"], check=False)
    user = run(["gh", "api", "user", "-q", ".login"], capture=True).stdout.strip()
    repo = f"{user}/{REPO_NAME}"
    say(f"Ingelogd als {user}.")

    step(2, "Telegram-bot koppelen")
    say("Plak het token dat je van @BotFather kreeg (ziet eruit als 1234567890:AAH...).")
    while True:
        token = ask("Bot-token:")
        me = telegram(token, "getMe")
        if me.get("ok"):
            say(f"Bot gevonden: @{me['result']['username']}")
            break
        say("Dit token werkt niet. Kopieer het opnieuw uit BotFather.")
    say("Open nu Telegram, zoek je bot op en stuur hem het bericht: hoi")
    chat_id = None
    for _ in range(60):
        ups = telegram(token, "getUpdates", timeout=0).get("result", [])
        for up in reversed(ups):
            msg = up.get("message")
            if msg and msg.get("chat", {}).get("type") == "private":
                chat_id = str(msg["chat"]["id"])
                break
        if chat_id:
            break
        time.sleep(3)
    if not chat_id:
        raise SystemExit("Geen bericht ontvangen. Stuur 'hoi' naar je bot en start setup.sh opnieuw.")
    say("Bericht ontvangen, Telegram is gekoppeld.")

    step(3, "Buffer koppelen (plaatst de clips op YouTube en Instagram)")
    say("Plak je Buffer API-sleutel (Buffer > Settings > API).")
    while True:
        bkey = ask("Buffer API-sleutel:")
        res = buffer_gql(bkey, "query { account { organizations { id name } } }")
        orgs = ((res.get("data") or {}).get("account") or {}).get("organizations")
        if orgs:
            break
        say(f"Deze sleutel werkt niet: {res.get('errors') or res}")
    channels = []
    for org in orgs:
        q = f'query {{ channels(input: {{ organizationId: "{org["id"]}" }}) {{ id name service }} }}'
        channels += ((buffer_gql(bkey, q).get("data") or {}).get("channels")) or []
    wanted = [c for c in channels if c["service"] in ("youtube", "instagram")]
    for c in channels:
        mark = "wordt gebruikt" if c in wanted else "overgeslagen"
        say(f"  {c['service']}: {c['name']} ({mark})")
    if not wanted:
        raise SystemExit("Geen YouTube- of Instagram-kanaal gevonden in Buffer. Koppel ze eerst in "
                         "Buffer en start setup.sh opnieuw.")
    lines = "channels:\n" + "".join(f'  - {{id: "{c["id"]}", service: "{c["service"]}"}}\n' for c in wanted)
    cfg_path = ROOT / "config.yml"
    cfg = cfg_path.read_text(encoding="utf-8")
    cfg = re.sub(r"channels:.*\Z", lines, cfg, flags=re.S)
    cfg_path.write_text(cfg, encoding="utf-8")

    step(4, "Gratis AI-sleutel voor het kiezen van de beste momenten (aanbevolen)")
    say("Plak je Gemini API-sleutel uit Google AI Studio, of druk op Enter om dit over te slaan.")
    gkey = ask("Gemini API-sleutel:", required=False)

    step(5, "Bron van je campagne (mag later ook via Telegram met /bron)")
    source = ask("Link naar het kanaal, de playlist of de video (Enter = later):", required=False)
    if source.startswith("http"):
        st_path = ROOT / "state" / "state.json"
        st = json.loads(st_path.read_text(encoding="utf-8"))
        if source not in st["sources"]:
            st["sources"].append(source)
        st_path.write_text(json.dumps(st, indent=2) + "\n", encoding="utf-8")

    step(6, "Repository op GitHub aanmaken")
    if not (ROOT / ".git").exists():
        run(["git", "init", "-q", "-b", "main"])
    run(["git", "add", "-A"])
    run(["git", "-c", "user.name=" + user, "-c", f"user.email={user}@users.noreply.github.com",
         "commit", "-q", "-m", "Clipper geinstalleerd"], check=False)
    if run(["gh", "repo", "view", repo], check=False, capture=True).returncode != 0:
        run(["gh", "repo", "create", repo, "--public", "--source", ".", "--remote", "origin", "--push"])
    else:
        run(["git", "remote", "remove", "origin"], check=False, capture=True)
        run(["git", "remote", "add", "origin", f"https://github.com/{repo}.git"])
        run(["git", "push", "-u", "origin", "main"])
    say(f"Repository staat op https://github.com/{repo}")

    step(7, "Sleutels veilig opslaan als GitHub-secrets")
    secrets = {"TELEGRAM_BOT_TOKEN": token, "TELEGRAM_CHAT_ID": chat_id, "BUFFER_API_KEY": bkey}
    if gkey:
        secrets["GEMINI_API_KEY"] = gkey
    for name, value in secrets.items():
        run(["gh", "secret", "set", name, "--repo", repo, "--body", value])
        say(f"  {name} opgeslagen")

    step(8, "Online opslag voor de clips aanzetten (GitHub Pages)")
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / ".nojekyll").write_text("")
        (Path(tmp) / "index.html").write_text("ok\n")
        (Path(tmp) / "clips").mkdir()
        (Path(tmp) / "clips" / ".keep").write_text("")
        run(["git", "init", "-q", "-b", "gh-pages"], cwd=tmp)
        run(["git", "add", "-A"], cwd=tmp)
        run(["git", "-c", "user.name=" + user, "-c", f"user.email={user}@users.noreply.github.com",
             "commit", "-q", "-m", "start"], cwd=tmp)
        run(["git", "push", "-q", "--force", f"https://github.com/{repo}.git", "gh-pages"], cwd=tmp)
    r = run(["gh", "api", "-X", "POST", f"repos/{repo}/pages", "-f", "source[branch]=gh-pages",
             "-f", "source[path]=/"], check=False, capture=True)
    if r.returncode != 0 and "already" not in (r.stdout + r.stderr).lower():
        say("Let op: GitHub Pages kon niet automatisch worden aangezet. Zet het met de hand aan: "
            f"https://github.com/{repo}/settings/pages > Branch: gh-pages > Save")
    else:
        say("GitHub Pages staat aan.")

    step(9, "Testbericht en eerste ronde")
    telegram(token, "sendMessage", chat_id=chat_id,
             text="De clipper is geinstalleerd. Elke nacht krijg je hier nieuwe clips met de knoppen "
                  "Plaatsen en Weggooien. Stuur /status voor een overzicht.")
    if source.startswith("http"):
        time.sleep(5)
        run(["gh", "workflow", "run", "generate.yml", "--repo", repo], check=False)
        say("De eerste ronde is gestart. Over 20 tot 40 minuten komen de eerste clips in Telegram.")
        say(f"Meekijken kan op https://github.com/{repo}/actions")
    else:
        say("Stuur je bot /bron <link> zodra je een campagne hebt. Daarna komen de clips elke nacht.")
    say("\nKlaar.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit("\nAfgebroken.")
