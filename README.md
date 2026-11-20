# Angebotsjäger – Einkaufsliste + Preisvergleich Lidl · REWE · ALDI SÜD

Web-App (PWA) für Windows, Android und iPhone. Kostenlos, privat. Ein Cloud-Job (GitHub Actions) holt 2× täglich die
Wochenangebote (marktguru) für deine PLZ, prüft per OpenStreetMap, ob die Märkte im Umkreis von 5 km liegen, und
vergleicht nach Preis pro kg/l. Die App zeigt den Bestpreis direkt an deinen Listen-Artikeln, öffnet beim Start ein
Popup und kann (optional) Push-Nachrichten schicken, auch wenn die App zu ist.

## Funktionen
- Einkaufsliste mit Kategorien, Abhaken, „Häufig gekauft“-Schnellwahl und Vorschlägen aus deinem Verlauf
- Automatische Tippfehler-Korrektur („Hakfleisch“ → „Hackfleisch“) mit „Rückgängig“; Wortschatz = Grundliste + Verlauf + Angebotsnamen
- Tab „Angebote“: Produkt suchen, alle Märkte nach Preis pro kg/l sortiert, ★ = Bestpreis
- Alles auf dem Gerät gespeichert (Liste, Verlauf). Im Repository steht nur die PLZ.

## Einrichtung (einmalig, ca. 15 Min.)
1. Kostenloses GitHub-Konto, neues Repo, diesen Ordner hochladen. Repo → Settings → Pages → Branch `main`, Ordner `/docs`.
   (Öffentliches Repo ist kostenlos und enthält nur Angebote und die PLZ, keine Zugangsdaten.)
2. PLZ in `config.json` prüfen (`"plz"`).
3. `python worker/gen_vapid.py` ausführen. **Public**-Key in `docs/config.js` eintragen, **Private**-Key als Secret `VAPID_PRIVATE_KEY`, deine Mail als Secret `VAPID_EMAIL`.
4. App-Adresse auf jedem Gerät öffnen und installieren (iPhone: Teilen → Zum Home-Bildschirm, ab iOS 16.4). Dann ⚙️ → „Push-Nachrichten aktivieren“:
   - Text 1 → Secret `PUSH_SUBSCRIPTIONS` (JSON-Liste, je Gerät ein Eintrag)
   - Text 2 → Secret `WATCHLIST` (Produkte deiner Liste; so steht die Liste nicht öffentlich im Repo und der Job weiß, wonach er suchen soll)
5. Actions → „Angebote abgleichen“ → Run workflow. Danach läuft es automatisch.
   Ohne Schritte 3–5 funktioniert die App trotzdem (Popup beim Öffnen), nur ohne Push bei geschlossener App.

## Lokal testen
`python worker/check.py --demo --no-push`, dann `python -m http.server -d docs` und http://localhost:8000 öffnen.

## Grenzen (ehrlich)
- Der Live-Abruf bei marktguru (`mg_keys`, `mg_search` in `worker/check.py`) ist **noch nicht mit echten Daten getestet**. marktguru hat keine offizielle Schnittstelle; ändert sich die Seite, zeigt die App „Fehler beim Abruf“ und die Funktion muss angepasst werden.
- Angebote sind PLZ-basiert; der 5-km-Filter prüft nur, ob die Kette per OpenStreetMap im Umkreis existiert, nicht die tagesaktuelle Filiale.
- Es werden nur Produkte abgefragt, die in `config.json` (`watchlist`, `zusatz_suchbegriffe`) oder im Secret `WATCHLIST` stehen.
- Nutzungsbedingungen der Datenquellen beachten: nur privat, geringe Abruffrequenz.
- Der Bestpreis wird nach Preis pro kg/l verglichen, wenn die Menge bekannt ist, sonst nach Packungspreis.
