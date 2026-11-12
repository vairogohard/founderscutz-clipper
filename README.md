# Founders Cutz clipper

Maakt elke nacht automatisch korte clips van de bronvideo's van je campagne, stuurt ze naar
Telegram ter controle en plaatst wat jij goedkeurt op YouTube Shorts en Instagram Reels.

## Hoe het werkt

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
| `/bron <link>` | Bron toevoegen: kanaal, playlist of video van je campagne |
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
