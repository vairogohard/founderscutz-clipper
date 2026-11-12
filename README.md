# Founders Cutz clipper

Maakt elke nacht automatisch korte clips van de bronvideo's van je campagne, stuurt ze naar
Telegram ter controle en plaatst wat jij goedkeurt op YouTube Shorts en Instagram Reels.

## Hoe het werkt

0. **Campagne kiezen (automatisch):** de bot leest het openbare campagne-overzicht van Content Rewards,
   kiest de beste clipcampagne (Engels, YouTube of Instagram, geen aanvraag nodig, genoeg budget, geen
   gokken of crypto), zet de bronlink en de verplichte tags klaar en meldt het in Telegram. Jij meldt je
   één keer aan via de link. Raakt het budget op, dan stapt de bot zelf over op de volgende.

1. **Elke nacht (GitHub Actions):** nieuwste video van je bron ophalen, spraak omzetten naar tekst,
   de sterkste momenten kiezen, knippen naar 9:16 met hooktitel en ondertitels.
2. **Elke ochtend (Telegram):** je krijgt de clips met de knoppen Plaatsen en Weggooien.
3. **Na Plaatsen:** de clip wordt via Buffer ingepland op het eerstvolgende vrije tijdstip
   (standaard 12:00, 17:00 en 20:00). Tikken worden elk kwartier verwerkt.

## Installeren

Draai in de VS Code-terminal, in deze map:

    bash setup.sh

Het script vraagt om je Telegram-bot-token, je Buffer API-sleutel en (optioneel) een Gemini-sleutel.
De rest gaat vanzelf: repository aanmaken, sleutels opslaan, opslag aanzetten, eerste ronde starten.

## Opdrachten in Telegram

| Opdracht | Wat het doet |
| --- | --- |
| `/zoek` | Nu de beste campagne zoeken en kiezen |
| `/campagne` | Huidige campagne en alternatieven tonen |
| `/kies <nummer>` | Een van de alternatieven kiezen |
| `/auto aan` of `/auto uit` | Automatisch campagnes kiezen aan of uit |
| `/bron <link>` | Zelf een bron toevoegen (zet automatisch kiezen uit) |
| `/bronnen` | Alle bronnen tonen |
| `/wisbron <nummer>` | Bron verwijderen |
| `/tekst <tekst>` | Verplichte campagnetekst of tags onder elke post |
| `/status` | Overzicht van wachtende en ingeplande clips |

## Instellingen

Alles staat in `config.yml`: aantal clips per nacht, plaatsingstijden, cliplengte, hashtags.
Na een wijziging: opslaan, committen en pushen.

## Goed om te weten

- Gebruik alleen bronmateriaal waarvoor je toestemming hebt (je campagne).
- De repository is openbaar. Je sleutels staan niet in de code maar in GitHub-secrets.
- De clips staan tijdelijk online op GitHub Pages zodat Buffer ze kan ophalen, en worden daarna
  automatisch opgeruimd.
- Een ronde met de hand starten: GitHub > Actions > Clips maken > Run workflow.
- Lokaal testen zonder internet: `python3 tests/selftest.py` en `python3 tests/test_poll.py`.

Lettertype: Anton (SIL Open Font License, zie `assets/fonts/OFL.txt`).
