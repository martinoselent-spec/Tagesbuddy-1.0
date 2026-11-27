# Tagesbuddy 1.0 – mein digitaler Sekretär

Ein „zweites Gedächtnis“, das proaktiv arbeitet: Es liest E-Mails, Kalender und
Dokumente, erkennt Termine, Aufgaben und Fristen, merkt sich alles und erinnert
rechtzeitig daran.

Es gibt zwei Varianten, die dasselbe Gedächtnis in Google Drive nutzen:

| | **Cloud** (dieser Ordner) | **Lokal** ([`lokal/`](lokal/README.md)) |
|---|---|---|
| KI | Claude, geplante Aufgabe auf claude.ai | Dein eigenes LLM über Ollama auf dem PC |
| Kosten | Claude-Abo | Strom, sonst kostenlos |
| Läuft | in der Cloud, PC kann aus sein | auf dem PC (Windows-Aufgabenplanung) |
| Konten | Connectoren (Gmail, Outlook, Kalender, Drive) | Google-API; Outlook per Weiterleitung an Gmail |
| Stärke | versteht auch komplizierte Schreiben sehr gut | unabhängig; strenge Code-Prüfung jeder Frist |

> Lass immer nur **eine** Variante täglich laufen, sonst überschreiben sie sich
> gegenseitig das Gedächtnis.

Die Cloud-Variante ist **keine eigene App**. Sie ist eine Arbeitsanweisung für Claude, das
über Connectoren auf die Konten zugreift und als **geplante Aufgabe** jeden
Morgen von selbst läuft.

## Wie es funktioniert

```
 Gmail ─┐                         ┌─► Morgen-Briefing (E-Mail an mich)
 Outlook┤                         ├─► Push-Nachricht aufs Handy (wenn dringend)
 Google ├─► Claude (täglich 6:35)  ┼─► Fristen als Kalendertermine mit Erinnerung
 Kalender                         ├─► Antwort-ENTWÜRFE (nie selbst gesendet)
 Drive ─┘          ▲              └─► Gedächtnis aktualisieren
                   │                        │
                   └──── Google Drive: Ordner „Tagesbuddy“ ◄┘
```

| Baustein | Wo | Zweck |
|---|---|---|
| Arbeitsanweisung | dieses Repo: [`CLAUDE.md`](CLAUDE.md), [`routinen/`](routinen/) | Was der Sekretär tut und was er darf |
| Gedächtnis | Google Drive → `Tagesbuddy/Tagesbuddy – Gedächtnis` | Offene Aufgaben, Fristen, Personen, Vorgänge |
| Deine Notizen | Google Drive → `Tagesbuddy/Tagesbuddy – Meine Notizen` | Hier schreibst **du** Aufgaben/Infos rein, der Sekretär übernimmt sie |
| Briefing-Archiv | Google Drive → `Tagesbuddy/Briefings/` | Ein Dokument pro Tag |
| Fristen | Google Kalender, Titel beginnt mit `⏰ Frist:` | Erinnerung 3 Tage und 1 Tag vorher |

> **Datenschutz:** Dieses Repository ist öffentlich. Hier stehen **keine**
> persönlichen Daten, nur die Anleitung. Alles Persönliche liegt in deinem
> privaten Google Drive und Kalender.

## Was der Sekretär darf (Stufe „Lesen + Entwürfe“)

- ✅ E-Mails (Gmail + Outlook), Kalender und Drive-Dokumente lesen
- ✅ Fristen und Erinnerungen als **eigene** Termine im Google Kalender anlegen
- ✅ Antwort-**Entwürfe** anlegen (Gmail/Outlook) – du prüfst und sendest selbst
- ✅ Gedächtnis- und Briefing-Dokumente im Ordner `Tagesbuddy` anlegen und alte Versionen davon in den Papierkorb legen
- ✅ Das Briefing per E-Mail **nur an dich selbst** senden
- ❌ Keine E-Mails an andere senden, nichts löschen, keine Einladungen annehmen/absagen, nichts bezahlen, keine fremden Dokumente ändern

## Benutzen

- **Automatisch:** Jeden Morgen um 6:35 Uhr (Europe/Berlin) startet die geplante Aufgabe „Tagesbuddy Morgen-Briefing“. Gegen 7 Uhr ist das Briefing per Mail und Push da.
- **Etwas merken lassen:** Schreib es in `Tagesbuddy – Meine Notizen` in Drive,
  z. B. `Bis 15.12. Steuererklärung abgeben` – beim nächsten Lauf wird daraus
  eine Aufgabe mit Frist und Kalendererinnerung.
- **Sofort fragen:** In einer Claude-Sitzung: „Was steht diese Woche an?“,
  „Welche Fristen laufen im Dezember ab?“, „Fasse den Vorgang X zusammen.“

## Dateien

- [`CLAUDE.md`](CLAUDE.md) – Grundregeln für den Sekretär (gilt in jeder Sitzung in diesem Repo)
- [`routinen/morgen-briefing.md`](routinen/morgen-briefing.md) – der tägliche Ablauf Schritt für Schritt
- [`vorlagen/gedaechtnis.md`](vorlagen/gedaechtnis.md) – Aufbau des Gedächtnis-Dokuments
- [`vorlagen/briefing.md`](vorlagen/briefing.md) – Aufbau des Morgen-Briefings
