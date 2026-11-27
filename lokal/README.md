# Tagesbuddy Lokal – digitaler Sekretär mit deinem eigenen LLM

Tagesbuddy Lokal läuft komplett auf deinem PC mit **Ollama**, ohne Claude und ohne
KI-Abo. Er liest jeden Morgen deine Mails, erkennt Fristen, Aufgaben und Termine,
trägt sie in den Google Kalender ein, pflegt das Gedächtnis in Google Drive und
schickt dir ein Morgen-Briefing.

```
 Gmail ◄── (Outlook leitet weiter)
   │
   ▼
 Tagesbuddy Lokal (Python, täglich 6:35, Windows-Aufgabenplanung)
   │  ① Mails + PDF-Anhänge holen        (Google-API)
   │  ② Fristen/Aufgaben/Termine herausziehen   ──►  Ollama (lokales LLM, JSON)
   │  ③ prüfen, Duplikate erkennen, priorisieren (fester Code, kein LLM)
   │  ④ Kalender: ⏰ Frist / 📌 Erinnerung
   │  ⑤ Antwort-ENTWÜRFE (nie gesendet)
   │  ⑥ Drive: Daten.json + „Tagesbuddy – Gedächtnis“ + Briefing-Archiv
   ▼
 Morgen-Briefing per Mail an dich (+ optional Push über ntfy)
```

**Warum das LLM nur „herausziehen“ darf:** Lokale Modelle sind gut, machen aber
eher Fehler als große Cloud-Modelle. Deshalb liefert das Modell nur strukturierte
Rohdaten (z. B. `{"datum": "2026-12-09", "was": "Stromanbieter anrufen"}`). Fester Code
prüft jedes Datum, erkennt Duplikate, berechnet Prioritäten und baut Gedächtnis
und Briefing. Ein Modell-Aussetzer kann so keine Fristen löschen und keine Mails
an Dritte schicken.

## Sicherheitsgrenzen (im Code fest eingebaut)

- Gesendet wird **nur an deine eigene Adresse** aus `config.toml`.
- Antworten an andere gibt es **nur als Entwurf**, und zwar nur bei Mails, die direkt an
  Gmail gingen, und nie bei Phishing-Verdacht.
- Kalender: nur eigene Einträge ohne Teilnehmer.
- Es wird **nichts gelöscht**: keine Mails, Termine oder Dateien.
- Mail-Inhalte gelten als Daten. Anweisungen darin werden ignoriert und Verdächtiges im
  Briefing gemeldet.

---

## Einrichtung (einmalig, ca. 30 Minuten)

### 1. Ollama und Modell

Ollama läuft schon. Lade ein Modell mit gutem Deutsch und sauberer JSON-Ausgabe.
Welches passt, hängt von deiner Grafikkarte ab:

| VRAM | Befehl |
|---|---|
| 8 GB | `ollama pull qwen2.5:7b-instruct` |
| 12–16 GB | `ollama pull qwen2.5:14b-instruct` |
| 24 GB | `ollama pull qwen2.5:32b-instruct` |

Andere Modelle mit „structured outputs“ (z. B. neuere Qwen- oder Llama-Versionen)
gehen auch. Trage den Namen in `config.toml` ein.

**Läuft Tagesbuddy auf einem anderen Gerät** in deinem Tailscale-Netz (z. B. Laptop
oder Mini-PC), muss Ollama auf dem Gaming-PC Verbindungen von außen annehmen:
Windows-Umgebungsvariable `OLLAMA_HOST=0.0.0.0` setzen und Ollama neu starten. In
`config.toml` steht dann `url = "http://<Tailscale-IP-des-Gaming-PCs>:11434"`.
Läuft alles auf dem Gaming-PC, bleibt es bei `http://localhost:11434`.

### 2. Outlook an Gmail weiterleiten

Seit 2024 erlaubt Microsoft bei privaten Outlook-Konten keinen einfachen
Passwort-Zugriff mehr. Am einfachsten ist die Weiterleitung:

outlook.live.com → ⚙️ Einstellungen → **E-Mail → Weiterleitung** → aktivieren →
deine Gmail-Adresse → **„Kopie der weitergeleiteten Nachrichten behalten“** anhaken.

Spam bleibt im Outlook-Junk-Ordner und wird nicht weitergeleitet. Was trotzdem
durchrutscht, sortiert der Gmail-Filter aus.

### 3. Google-Zugang (Google Cloud, kostenlos)

1. <https://console.cloud.google.com> → oben **Neues Projekt** → Name `Tagesbuddy`.
2. **APIs & Dienste → Bibliothek**: aktivieren:
   **Gmail API**, **Google Calendar API**, **Google Drive API**.
3. **Google Auth Platform → Branding / Zustimmungsbildschirm**: Zielgruppe **Extern**,
   App-Name `Tagesbuddy`, deine Gmail-Adresse als Support- und Entwickler-Kontakt.
4. **Zielgruppe → Testnutzer**: deine Gmail-Adresse hinzufügen. Dann
   **„App veröffentlichen“ → In Produktion**.
   ⚠️ Wichtig: Im Status „Test“ läuft die Anmeldung nach 7 Tagen ab und der
   Sekretär bleibt stehen. Eine Überprüfung durch Google ist für die eigene
   Nutzung nicht nötig.
5. **Clients → Client erstellen → Desktop-App** → JSON herunterladen → als
   **`credentials.json`** in diesen Ordner (`lokal`) legen.

Beim ersten Anmelden zeigt Google „Google hat diese App nicht überprüft“. Klicke auf
**Erweitert → Weiter zu Tagesbuddy**. Das ist deine eigene App, die Warnung ist
hier normal.

### 4. Installieren (Windows, PowerShell im Ordner `lokal`)

Voraussetzung: [Python 3.11+](https://www.python.org/downloads/) (bei der
Installation „Add to PATH“ anhaken).

```powershell
powershell -ExecutionPolicy Bypass -File scripts\einrichten.ps1
```

Das Skript legt eine virtuelle Umgebung an, installiert die Pakete, öffnet
`config.toml` zum Ausfüllen, startet den Google-Login im Browser und testet alles.

In `config.toml` musst du mindestens eintragen:
- `email`: deine Gmail-Adresse
- `modell`: das Modell aus Schritt 1
- `ordner_id`: ID des Drive-Ordners „Tagesbuddy“. Du findest sie in der Adresszeile:
  `drive.google.com/drive/folders/<ID>`

### 5. Testen

```powershell
.venv\Scripts\python.exe -m tagesbuddy pruefen          # Verbindungen
.venv\Scripts\python.exe -m tagesbuddy lauf --trocken   # alles auswerten, NICHTS ändern
.venv\Scripts\python.exe -m tagesbuddy lauf             # echter Lauf mit Briefing-Mail
```

Der Trockenlauf zeigt dir das Briefing in der Konsole. So siehst du, wie gut dein
Modell Fristen erkennt, bevor irgendetwas im Kalender landet.

### 6. Täglich automatisch

```powershell
powershell -ExecutionPolicy Bypass -File scripts\aufgabe_planen.ps1 -Uhrzeit 06:35
```

Die Aufgabe läuft auch ohne Anmeldung am PC. War der PC aus, holt sie den Lauf beim
nächsten Start nach. Das Protokoll steht in `logs\tagesbuddy.log`. Bricht ein Lauf ab,
bekommst du eine Mail „⚠️ Tagesbuddy: Lauf fehlgeschlagen“.

### 7. Optional: Push aufs Handy

Installiere die App **ntfy** (Android/iOS) und abonniere ein Thema mit zufälligem
Namen, z. B. `tagesbuddy-k7x2q9`. Trage dasselbe Thema in `config.toml` unter
`[push] ntfy_thema` ein. Hinweis: Wer den Themen-Namen kennt, kann mitlesen. Wähle
ihn also lang und zufällig.

---

## Benutzen

- **Etwas merken lassen:** In das Google Doc „Tagesbuddy – Meine Notizen“ unter die
  Trennlinie schreiben, z. B. `Bis 15.12. Steuererklärung abgeben` oder
  `erledigt: Stromanbieter angerufen`.
- **Gedächtnis ansehen:** „Tagesbuddy – Gedächtnis“ in Drive. Es wird aus
  `Tagesbuddy – Daten.json` erzeugt, Änderungen von Hand werden überschrieben.
- **Wechsel von der Cloud-Version:** Beide Versionen nutzen denselben Drive-Ordner.
  Lass nur **eine** täglich laufen und pausiere die andere, sonst überschreiben sie
  sich gegenseitig das Gedächtnis.

## Entwicklung

```bash
pip install -r requirements.txt pytest
python -m pytest -q        # Tests mit Fake-LLM und Fake-Google, ohne Netz
```

| Datei | Aufgabe |
|---|---|
| `tagesbuddy/run.py` | Tagesablauf |
| `tagesbuddy/extract.py` | Prompts, JSON-Schemata, Prüfung der Modellausgabe |
| `tagesbuddy/store.py` | Gedächtnis-Datenmodell, Duplikate, Prioritäten, Gedächtnis-Text |
| `tagesbuddy/briefing.py` | Briefing (HTML-Mail, Text, Push) |
| `tagesbuddy/google_api.py` | Gmail, Kalender, Drive (inkl. Sicherheitsgrenzen) |
| `tagesbuddy/llm.py` | Ollama-Client mit strukturierter Ausgabe |
