#!/usr/bin/env bash
# YouTube-cookies (opnieuw) instellen. Draai in de VS Code-terminal van je clipper:
#   bash tools/cookies.sh            (daarna het cookiebestand in de terminal slepen)
set -e
cd "$(dirname "$0")/.."

FILE="$1"
if [ -z "$FILE" ]; then
  echo "Sleep je cookiebestand (bijvoorbeeld www.youtube.com_cookies.txt) hierheen en druk op Enter:"
  read -r FILE
fi
FILE="${FILE%\"}"; FILE="${FILE#\"}"; FILE="${FILE%\'}"; FILE="${FILE#\'}"
FILE="$(echo "$FILE" | sed -e 's/[[:space:]]*$//' -e 's/\\ / /g')"

if [ ! -f "$FILE" ]; then
  echo "Bestand niet gevonden: $FILE"; exit 1
fi
if ! head -c 200 "$FILE" | grep -qi "cookie file"; then
  echo "Dit lijkt geen cookies.txt-bestand (Netscape-formaat). Exporteer opnieuw met 'Get cookies.txt LOCALLY'."
  exit 1
fi
if ! grep -q "youtube.com" "$FILE"; then
  echo "Er staan geen YouTube-cookies in dit bestand. Exporteer op youtube.com/robots.txt."; exit 1
fi
if ! grep -qE "(__Secure-3PSID|LOGIN_INFO|SID)" "$FILE"; then
  echo "Let op: het lijkt erop dat je niet was ingelogd toen je exporteerde. Ik ga toch door."
fi

REPO="$(gh repo view --json nameWithOwner -q .nameWithOwner)"
gh secret set YT_COOKIES --repo "$REPO" < "$FILE"
echo "Cookies veilig opgeslagen als GitHub-secret."

rm -f "$FILE"
echo "Het cookiebestand op je Mac is verwijderd (het staat nu alleen nog als geheim op GitHub)."

echo "Clipronde starten..."
gh workflow run generate.yml --repo "$REPO" && echo "Gestart. Over 20 tot 40 minuten komen de clips in Telegram."
