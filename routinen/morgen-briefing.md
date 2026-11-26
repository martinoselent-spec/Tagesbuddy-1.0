# Routine: Morgen-Briefing (täglich ~7:00 Europe/Berlin)

Diese Datei beschreibt, was die geplante Aufgabe jeden Morgen tut. Der Text der
geplanten Aufgabe selbst ist eine Kopie dieser Schritte, ergänzt um die private
E-Mail-Adresse des Nutzers. Die Adresse steht absichtlich **nicht** hier, weil
das Repo öffentlich ist. Es gelten immer die Regeln aus [`../CLAUDE.md`](../CLAUDE.md).

## 0. Vorbereitung
- Heutiges Datum und Uhrzeit in Europe/Berlin bestimmen.
- In Google Drive den Ordner `Tagesbuddy` suchen (`title = 'Tagesbuddy'`,
  Ordner-MIME-Typ). Falls er fehlt: anlegen, darin den Unterordner `Briefings`
  und ein leeres Google Doc `Tagesbuddy – Meine Notizen` anlegen.
- `Tagesbuddy – Gedächtnis` lesen (neueste Version). Daraus übernehmen:
  „Zuletzt verarbeitet“, offene Aufgaben, Fristen, Vorgänge, Personen.
- `Tagesbuddy – Meine Notizen` lesen. Neue Einträge seit dem letzten Lauf
  werden Aufgaben/Fristen. Das Dokument selbst nie verändern.

## 1. Einsammeln (nur lesen)
Zeitraum: seit „Zuletzt verarbeitet“ minus 1 Tag Überlappung (beim ersten Lauf:
letzte 14 Tage). Bereits bekannte Vorgänge über Betreff, Absender und Datum
erkennen und nicht doppelt anlegen.

- **Gmail:** `in:inbox after:JJJJ/MM/TT -category:promotions -category:social`.
  Relevante Threads mit `get_thread` vollständig lesen.
- **Outlook:** `outlook_email_search` mit `afterDateTime`, Seiten durchblättern.
  Relevante Mails mit `read_resource` lesen.
- **Google Kalender:** Termine heute bis +14 Tage. Offene Einladungen
  (`responseStatus = needsAction`) merken.
- **Outlook-Kalender:** Termine heute bis +14 Tage.
- **Google Drive:** in letzter Zeit geänderte Dateien (`list_recent_files`).
  Nur Dokumente mit möglichen Fristen lesen (Bescheide, Verträge, Widersprüche,
  Rechnungen, Schreiben von Behörden, Gerichten oder Anwälten).

## 2. Auswerten
Für jede relevante Information festhalten:
- Art: Frist / Aufgabe / Termin / Info / ⚠️ Auffällig
- Was genau, bis wann (Datum; bei errechneten Fristen „(errechnet)“), Quelle
  (Konto + Absender + Betreff + Link), Priorität [DRINGEND]/[BALD]/[SPÄTER]
- Vorgang (z. B. „Anwalt – Verfahren“, „Mobilfunkvertrag“), damit
  zusammengehörige Mails gebündelt werden.

Erledigtes erkennen: Wenn eine gesendete Mail, ein Kalendereintrag oder eine
Notiz zeigt, dass eine Aufgabe erledigt ist, diese als erledigt markieren.

## 3. Handeln (nur erlaubte Aktionen)
1. **Fristen → Google Kalender:** Für jede neue Frist mit Datum zuerst per
   `search_events` nach `⏰ Frist` + Stichwort suchen, damit nichts doppelt
   angelegt wird. Fehlt sie, einen ganztägigen Termin anlegen:
   - Titel: `⏰ Frist: <kurz, was zu tun ist>`
   - Beschreibung: Quelle + Link + was zu tun ist + „angelegt von Tagesbuddy“
   - Erinnerungen (`overrideReminders`): Popup und E-Mail 3 Tage vorher
     (4320 min) und 1 Tag vorher (1440 min)
   - `availability`: `AVAILABILITY_FREE`, keine Teilnehmer
2. **Termine aus Mails**, die noch nicht im Kalender stehen: als
   `📌 Erinnerung: …` mit Uhrzeit anlegen (keine Teilnehmer, keine Einladungen).
3. **Antwort-Entwürfe:** Nur wenn eine Mail eindeutig eine Antwort vom Nutzer
   erwartet: Entwurf im selben Konto anlegen (Gmail `create_draft` bzw.
   Outlook `outlook_create_reply_draft`). Kurz, höflich, Sie-Form, mit
   Platzhaltern `[…]` für alles, was der Nutzer selbst entscheiden muss.
   **Niemals absenden.**
4. **Gedächtnis aktualisieren:** Neues Google Doc `Tagesbuddy – Gedächtnis` im
   Ordner `Tagesbuddy` nach [`../vorlagen/gedaechtnis.md`](../vorlagen/gedaechtnis.md)
   anlegen (Text-Upload, **ohne 4-Byte-Emojis**). Danach die vorherige Version
   in den Papierkorb legen.
5. **Briefing archivieren:** Google Doc `Briefing JJJJ-MM-TT` im Unterordner
   `Briefings` anlegen.

## 4. Benachrichtigen
- **E-Mail an den Nutzer selbst** (Gmail `send_message`, nur an die eigene
  Adresse) mit dem Briefing nach [`../vorlagen/briefing.md`](../vorlagen/briefing.md)
  als `htmlBody`. Betreff: `☀️ Tagesbuddy <Wochentag, TT.MM.>: <n> dringend, <m> Fristen`
- **Push:** Wenn es [DRINGEND]-Punkte gibt, den letzten Satz der Antwort so formulieren,
  dass er als Push-Nachricht taugt, z. B. „🔴 Heute: Anwaltstermin 10:30;
  Frist Widerspruch morgen“.

## 5. Abschluss
Kurze Zusammenfassung als Antwort: was gelesen, was angelegt (Kalender,
Entwürfe, Dokumente), was auffällig war. Keine privaten Inhalte ins Repo
committen.
