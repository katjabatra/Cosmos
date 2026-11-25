# CLAUDE.md — Cosmos / Stammgast App

Lies diese Datei zu Beginn jeder Session. Sie enthält alles Wichtige zum Projekt.

## Projekt
Native iOS + Android App für die Gaststätte Cosmos in Hannover.
**Deadline: 16. Dezember 2026** (App Store Submission spätestens ~10. Dez)
Motto: Qualität vor Speed — keine halbfertigen Features in main.

## Auftraggeber / Auftragnehmerin
- **Kosta Bliamis** (nicht Costa!), Gaststätte Cosmos, Otto-Wels-Straße 4, 30451 Hannover
- **Katja Batra**, Auftragnehmerin, Hannover

## Repo-Struktur
```
Cosmos/
├── backend/        # Python / FastAPI
│   ├── main.py
│   └── requirements.txt
├── frontend/       # ALTES HTML — wird durch React Native ersetzt
│   ├── index.html
│   └── admin.html
├── mobile/         # NEU: React Native / Expo App (wird hier angelegt)
├── Procfile
└── CLAUDE.md
```

## Tech Stack (festgelegt)
- **Mobile App:** React Native + Expo (eine Codebasis → PWA + App Store)
- **Backend:** Python / FastAPI auf Render.com (Frankfurt) — bleibt, wird erweitert
- **Datenbank:** PostgreSQL auf Render.com
- **Live URL:** cosmos-queue.onrender.com
- **Musik:** Spotify Web API (via Spotipy)
- **Zahlungen:** Stripe für Vote-Käufe (Konto auf Kosta Bliamis)
- **Getränke-Bezahlung:** PayPal Later
- **Gutscheine:** Token/Code-System, Kosta erstellt im Admin-Panel

## Was bereits läuft — NICHT anfassen ohne Grund
- Spotify OAuth + Token-Refresh + Keepalive-Thread
- Queue anzeigen + Song hinzufügen (Limit: 3/Tag pro IP)
- Voting (3 Gratis-Votes/Tag pro IP, Flammen-Anzeige, Queue nach Votes sortiert)
- Song-Suche via Spotify
- Genre-Auswahl + Treppchen (Top 3 Genres)
- QR-Scan-Tracking
- Top Songs / Top Genres Stats
- Admin Dashboard (admin.html)
- Tagescode-Check (aktuell hardcoded "COSMOS" im Frontend → muss ins Backend!)

## Design-System (immer einhalten)
- Hintergrund: `#0d0a14` (Dunkelviolett/Schwarz)
- Akzent: `#c97ef5` (Lila/Pink)
- Surface: `#1a1425` / `#241a33`
- Text: `#f0eaf8`, Muted: `#9988bb`
- Fonts: Caveat (Headlines, Buttons), Space Mono (Logo)
- Stil: dunkle Karten, abgerundete Ecken, Glow-Effekte

## Was gebaut wird (Reihenfolge = Priorität)

### Phase 1: Expo-Setup + bestehende Features portieren
- [ ] Expo-Projekt unter `mobile/` anlegen
- [ ] CodeScreen (Tagescode vom Backend, nicht hardcoded)
- [ ] StartScreen
- [ ] QueueScreen (Suche, Queue, Voting, Flammen)
- [ ] GenreScreen (Genre-Auswahl, Treppchen)
- [ ] API-Verbindung zum bestehenden Backend

### Phase 2: Neue Features
- [ ] Onboarding: Vorname + Lieblingsgenre (einmalig, serverseitig)
- [ ] Stammgast-Status: wer die App im Store kauft, ist Stammgast (sofort nach Kauf)
- [ ] Getränkekarte (Admin pflegt, Gast sieht App-Preis vs. Normalpreis)
- [ ] Gutschein/Token-System
- [ ] Kellner-Ansicht (PIN, Tisch, Gast → Positionen zuordnen)
- [ ] Pflichthinweise vor Käufen (Anwalt-Pflicht: Preisanzeige + Bestätigungsdialog)
- [ ] apple-touch-icon.png (180×180px) ins Root

### Phase 3: Store-Submission (~10. Dez)
- [ ] App Store Connect (Apple Developer Account: Kosta zahlt 99$/Jahr)
- [ ] Google Play Console
- [ ] Screenshots, App-Beschreibung, Datenschutzlink
- [ ] Submission

### Phase 4: Januar 2027
- [ ] TSE-Schnittstelle (Fiskaly) — nach Klärung durch Kostas Steuerberater
- [ ] PayPal Later technische Integration

## Stammgast-Definition (wichtig!)
Stammgast = wer die native App kostenpflichtig aus dem App Store / Google Play kauft.
PWA-Nutzer sind KEINE Stammgäste. Sobald gekauft = Stammgast. Fertig.

## Rechtliches (Anwalt-Termin 11.11.2026)
- AGBs: Kostas Aufgabe (IT-Recht Kanzlei)
- Datenschutzerklärung: Kosta verantwortlich, Katja Auftragsverarbeiterin
- AVV: noch abzuschließen
- Kein digitaler Bierdeckel (Fremdgeldverwaltung) → PayPal Later
- Votes: rechtlich OK
- Pflichthinweise vor jedem Kauf: Pflicht laut Anwalt

## Arbeitsweise
- Diese Datei immer zuerst lesen
- Nach jedem Merge: Katja sagt "bitte unabhängig reviewen" → neuer Review-Agent
- Kosta heißt Kosta (nicht Costa, nicht Konstantino im Code)
- Backend-Endpoints stabil halten — kein Breaking Change ohne Absprache
