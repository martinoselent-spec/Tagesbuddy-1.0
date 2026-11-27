"""Der tägliche Ablauf: einsammeln → auswerten → handeln → benachrichtigen."""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta

from . import extract, notify
from .briefing import Briefing, Lauf, erstellen, von_name
from .config import Config
from .llm import LLMFehler
from .store import Aufgabe, Daten, Frist, Person, gedaechtnis_text, hash_zeile

log = logging.getLogger(__name__)

NOTIZ_TRENNER = "Deine Einträge ab hier"


def notiz_zeilen(text: str) -> list[str]:
    """Zeilen, die der Nutzer selbst geschrieben hat (nach der Trennlinie)."""
    if NOTIZ_TRENNER in text:
        text = text.split(NOTIZ_TRENNER, 1)[1]
    zeilen = []
    for z in text.splitlines():
        z = z.strip().lstrip("-*•").strip()
        if len(z) >= 3 and not set(z) <= set("-=_ "):
            zeilen.append(z)
    return zeilen


def ausfuehren(cfg: Config, google, llm, jetzt: datetime, trocken: bool = False) -> Briefing:
    heute: date = jetzt.date()
    lauf = Lauf()

    # ---------------------------------------------------------------- 0. Gedächtnis laden
    ordner = cfg.ordner_id or google.ordner("Tagesbuddy")
    daten_id = google.finden(cfg.daten_titel, ordner)
    daten = Daten.aus_dict(google.json_lesen(daten_id)) if daten_id else Daten()
    log.info("Gedächtnis geladen: %d Fristen, %d Aufgaben", len(daten.fristen), len(daten.aufgaben))

    # ---------------------------------------------------------------- 1. Meine Notizen
    notizen_id = google.finden(cfg.notizen_titel, ordner)
    if notizen_id:
        neu = [z for z in notiz_zeilen(google.text_lesen(notizen_id)) if hash_zeile(z) not in daten.notizen_hashes]
        if neu:
            try:
                n = extract.notizen_auswerten(llm, neu, daten.offene(), heute)
                lauf.erledigt += daten.erledigen(n["erledigt_ids"], heute)
                for f in n["fristen"]:
                    daten.frist_hinzufuegen(Frist(datum=f["datum"], was=f["was"], errechnet=f["errechnet"],
                                                  quelle="Meine Notizen", wichtig=True))
                for a in n["aufgaben"]:
                    daten.aufgabe_hinzufuegen(Aufgabe(was=a, quelle="Meine Notizen", seit=heute.isoformat()))
                daten.notizen_sekretaer += [f"{heute:%d.%m.} {m}" for m in n["merken"]]
                daten.notizen_hashes += [hash_zeile(z) for z in neu]
                lauf.notizen = len(neu)
            except LLMFehler as e:
                lauf.fehler.append(f"Notizen konnten nicht ausgewertet werden ({e})")
    else:
        lauf.fehler.append(f"Dokument „{cfg.notizen_titel}“ nicht gefunden")

    # ---------------------------------------------------------------- 2. Mails einsammeln
    if daten.zuletzt_verarbeitet:
        seit = datetime.fromisoformat(daten.zuletzt_verarbeitet) - timedelta(days=1)
    else:
        seit = jetzt - timedelta(days=cfg.erster_lauf_tage)
    try:
        mails = [m for m in google.mails_seit(seit, cfg.max_mails) if m["id"] not in daten.verarbeitete_ids]
    except Exception as e:
        log.exception("Gmail-Abruf fehlgeschlagen")
        mails = []
        lauf.fehler.append(f"Gmail nicht abrufbar ({e})")
    lauf.gelesen = len(mails)

    # ---------------------------------------------------------------- 3. Auswerten
    neue_termine: list[tuple[dict, dict]] = []
    for mail in mails:
        try:
            e = extract.mail_auswerten(llm, mail, list(daten.vorgaenge), heute)
        except LLMFehler as ex:
            lauf.fehler.append(f"Mail „{mail.get('betreff', '')[:60]}“ nicht auswertbar ({ex})")
            continue  # nicht als verarbeitet markieren -> nächster Lauf versucht es erneut
        daten.verarbeitete_ids.append(mail["id"])
        name = von_name(mail.get("von", ""))
        quelle = f"{name}, „{mail.get('betreff', '')[:80]}“, {mail.get('datum', '')[:10]}"
        if e.verdacht:
            lauf.auffaellig.append(f"{name}: {mail.get('betreff', '')[:80]} – {e.verdacht}")
        if not e.relevant:
            continue
        daten.verlauf_eintragen(e.vorgang, mail.get("datum", heute.isoformat())[:10], e.zusammenfassung[:200])
        for f in e.fristen:
            if daten.frist_hinzufuegen(Frist(datum=f["datum"], was=f["was"], errechnet=f["errechnet"],
                                             vorgang=e.vorgang, quelle=quelle, wichtig=e.wichtig)):
                lauf.neue_fristen += 1
        for a in e.aufgaben:
            daten.aufgabe_hinzufuegen(Aufgabe(was=a, vorgang=e.vorgang, quelle=quelle, seit=heute.isoformat()))
        for p in e.personen:
            daten.person_hinzufuegen(Person(name=p["name"], rolle=p["rolle"], kontakt=p["kontakt"], vorgang=e.vorgang))
        neue_termine += [(t, mail) for t in e.termine]

        entwurf = False
        if cfg.entwuerfe and e.antwort_erwartet and mail.get("an_mich") and not e.verdacht:
            text = extract.entwurf_schreiben(llm, mail)
            if text and not trocken:
                try:
                    google.entwurf_anlegen(mail, text)
                    lauf.entwuerfe += 1
                    entwurf = True
                except Exception as ex:
                    lauf.fehler.append(f"Entwurf nicht angelegt ({ex})")
        if e.fristen or e.aufgaben or e.antwort_erwartet or e.kategorie in ("frist", "aufgabe", "termin", "auffaellig"):
            lauf.relevant.append({"von_name": name, "betreff": mail.get("betreff", "")[:90],
                                  "zusammenfassung": e.zusammenfassung[:200], "link": mail.get("link", ""),
                                  "entwurf": entwurf})

    # ---------------------------------------------------------------- 4. Kalender
    if cfg.kalender_eintragen:
        for f in daten.fristen:
            if f.erledigt or f.kalender_id or date.fromisoformat(f.datum) < heute:
                continue
            try:
                vorhanden = google.eintrag_suchen(date.fromisoformat(f.datum), f.was)
                if vorhanden:
                    f.kalender_id = vorhanden
                elif not trocken:
                    beschr = f"{f.was}\nVorgang: {f.vorgang or '-'}\nQuelle: {f.quelle or '-'}"
                    if f.errechnet:
                        beschr += "\nDatum errechnet – bitte am Original prüfen."
                    f.kalender_id = google.frist_eintragen(f.datum, f.was, beschr, f.wichtig)
                    lauf.kalender += 1
            except Exception as ex:
                lauf.fehler.append(f"Kalendereintrag für „{f.was[:50]}“ fehlgeschlagen ({ex})")
        for t, mail in neue_termine:
            try:
                if not google.eintrag_suchen(date.fromisoformat(t["datum"]), t["titel"]) and not trocken:
                    google.erinnerung_eintragen(t["datum"], t["uhrzeit"], t["titel"], t["ort"],
                                                f"Aus Mail: {von_name(mail.get('von', ''))}, „{mail.get('betreff', '')}“")
                    lauf.kalender += 1
            except Exception as ex:
                lauf.fehler.append(f"Termin „{t['titel'][:50]}“ nicht eingetragen ({ex})")

    try:
        termine = google.termine(heute, heute + timedelta(days=14))
    except Exception as ex:
        termine = []
        lauf.fehler.append(f"Kalender nicht lesbar ({ex})")

    # ---------------------------------------------------------------- 5. Speichern
    daten.zuletzt_verarbeitet = jetzt.isoformat(timespec="seconds")
    daten.aufraeumen(heute)
    gedaechtnis = gedaechtnis_text(daten, termine, jetzt)

    links = {"Meine Notizen": _doc_link(notizen_id)}
    ged_id = google.finden(cfg.gedaechtnis_titel, ordner)
    links["Gedächtnis"] = _doc_link(ged_id)
    briefing = erstellen(daten, termine, lauf, jetzt, cfg.anrede, links)

    if trocken:
        log.info("Trockenlauf – nichts gespeichert, nichts gesendet.")
        return briefing

    google.text_schreiben(cfg.daten_titel, ordner, json.dumps(daten.als_dict(), ensure_ascii=False, indent=1),
                          als_doc=False, fid=daten_id)
    ged_id = google.text_schreiben(cfg.gedaechtnis_titel, ordner, gedaechtnis, als_doc=True, fid=ged_id)
    try:
        b_ordner = google.ordner(cfg.briefings_ordner_titel, ordner)
        google.text_schreiben(f"Briefing {heute.isoformat()}", b_ordner, briefing.text, als_doc=True,
                              fid=google.finden(f"Briefing {heute.isoformat()}", b_ordner))
    except Exception as ex:
        log.warning("Briefing-Archiv fehlgeschlagen: %s", ex)

    # ---------------------------------------------------------------- 6. Benachrichtigen
    google.an_mich_senden(briefing.betreff, briefing.html, briefing.text)
    notify.push(cfg.ntfy_server, cfg.ntfy_thema, briefing.betreff, briefing.push, dringend=briefing.dringend > 0)
    return briefing


def _doc_link(fid: str | None) -> str:
    return f"https://docs.google.com/document/d/{fid}/edit" if fid else ""
