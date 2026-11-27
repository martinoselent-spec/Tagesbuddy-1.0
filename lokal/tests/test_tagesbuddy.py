"""Tests ohne Netz: Fake-LLM und Fake-Google simulieren einen kompletten Lauf."""
from __future__ import annotations

import base64
import json
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from tagesbuddy import extract, mailparse
from tagesbuddy.config import Config
from tagesbuddy.llm import LLMFehler
from tagesbuddy.run import ausfuehren, notiz_zeilen
from tagesbuddy.store import (BALD, DRINGEND, SPAETER, Daten, Frist, aehnlich,
                              gedaechtnis_text, ohne_emoji, prioritaet)

TZ = ZoneInfo("Europe/Berlin")
JETZT = datetime(2026, 11, 27, 6, 35, tzinfo=TZ)
HEUTE = JETZT.date()


# --------------------------------------------------------------------------- Fakes
class FakeLLM:
    def __init__(self, antworten: dict[str, dict], entwurf: str = "Sehr geehrte Damen und Herren, [Antwort]"):
        self.antworten, self.entwurf, self.anfragen = antworten, entwurf, []

    def json(self, system, nutzer, schema):
        self.anfragen.append(nutzer)
        for schluessel, antwort in self.antworten.items():
            if schluessel in nutzer:
                if isinstance(antwort, Exception):
                    raise antwort
                return antwort
        return {"relevant": False, "kategorie": "werbung", "vorgang": "", "zusammenfassung": "",
                "rechtlich_oder_finanziell": False, "fristen": [], "aufgaben": [], "termine": [],
                "personen": [], "antwort_erwartet": False, "verdacht": ""}

    def text(self, system, nutzer):
        return self.entwurf


class FakeGoogle:
    def __init__(self, mails, notizen="", daten=None, termine=None):
        self.mails, self.termine_liste = mails, termine or []
        self.dateien = {"ordner": ("Tagesbuddy", ""), "n1": ("Tagesbuddy – Meine Notizen", notizen)}
        if daten is not None:
            self.dateien["d1"] = ("Tagesbuddy – Daten.json", json.dumps(daten))
        self.gesendet, self.entwuerfe, self.kalender, self.zaehler = [], [], [], 0

    def ordner(self, titel, eltern=None):
        return self.finden(titel) or self._neu(titel, "")

    def finden(self, titel, eltern=None, mime=None):
        return next((k for k, (t, _) in self.dateien.items() if t == titel), None)

    def _neu(self, titel, inhalt):
        self.zaehler += 1
        fid = f"neu{self.zaehler}"
        self.dateien[fid] = (titel, inhalt)
        return fid

    def json_lesen(self, fid):
        return json.loads(self.dateien[fid][1])

    def text_lesen(self, fid):
        return self.dateien[fid][1]

    def text_schreiben(self, titel, eltern, text, als_doc, fid=None):
        if fid:
            self.dateien[fid] = (titel, text)
            return fid
        return self._neu(titel, text)

    def mails_seit(self, seit, maximal):
        self.seit = seit
        return self.mails[:maximal]

    def entwurf_anlegen(self, mail, text):
        self.entwuerfe.append((mail["id"], text))
        return "draft1"

    def an_mich_senden(self, betreff, html, text):
        self.gesendet.append((betreff, html, text))

    def termine(self, von, bis):
        return self.termine_liste

    def eintrag_suchen(self, tag, text):
        for k in self.kalender:
            if k["datum"] == tag.isoformat() and aehnlich(k["titel"], text):
                return k["id"]
        return None

    def frist_eintragen(self, datum, was, beschreibung, wichtig):
        self.kalender.append({"id": f"ev{len(self.kalender)}", "datum": datum, "titel": was, "wichtig": wichtig})
        return self.kalender[-1]["id"]

    def erinnerung_eintragen(self, datum, uhrzeit, titel, ort, beschreibung):
        self.kalender.append({"id": f"ev{len(self.kalender)}", "datum": datum, "titel": titel, "uhrzeit": uhrzeit})
        return self.kalender[-1]["id"]


def cfg() -> Config:
    return Config(email="ich@gmail.com", anrede="Hallo Test", ordner_id="ordner", basis=Path("/tmp"))


def mail(mid, betreff, text="", an="ich@gmail.com", von="Firma <info@firma.de>"):
    return {"id": mid, "thread_id": "t" + mid, "von": von, "an": an, "betreff": betreff,
            "datum": "2026-11-26 10:00", "message_id": f"<{mid}@x>", "an_mich": "ich@gmail.com" in an,
            "link": "", "text": text, "anhaenge": ""}


def antwort(**k):
    basis = {"relevant": True, "kategorie": "frist", "vorgang": "Test", "zusammenfassung": "Zusammenfassung",
             "rechtlich_oder_finanziell": False, "fristen": [], "aufgaben": [], "termine": [], "personen": [],
             "antwort_erwartet": False, "verdacht": ""}
    basis.update(k)
    return basis


# --------------------------------------------------------------------------- Store
def test_prioritaet():
    assert prioritaet(Frist(datum="2026-11-28", was="x"), HEUTE) == DRINGEND
    assert prioritaet(Frist(datum="2026-12-02", was="x"), HEUTE) == BALD
    assert prioritaet(Frist(datum="2026-12-20", was="x"), HEUTE) == SPAETER
    assert prioritaet(Frist(datum="2026-12-09", was="x", wichtig=True), HEUTE) == DRINGEND


def test_frist_duplikate_werden_erkannt():
    d = Daten()
    assert d.frist_hinzufuegen(Frist(datum="2026-12-09", was="Stromanbieter anrufen wegen Kündigung"))
    assert d.frist_hinzufuegen(Frist(datum="2026-12-09", was="Kündigung Stromanbieter telefonisch bestätigen anrufen")) is None
    assert d.frist_hinzufuegen(Frist(datum="2026-12-10", was="Stromanbieter anrufen wegen Kündigung"))  # anderes Datum
    assert len(d.fristen) == 2


def test_serialisierung_rundlauf():
    d = Daten(zuletzt_verarbeitet="2026-11-26T11:45:00+01:00")
    d.frist_hinzufuegen(Frist(datum="2026-12-09", was="Widerspruch", wichtig=True))
    d.verlauf_eintragen("Insolvenz", "2026-11-26", "Einladung erhalten", "Verfahren")
    d2 = Daten.aus_dict(json.loads(json.dumps(d.als_dict())))
    assert d2.fristen[0].was == "Widerspruch" and d2.fristen[0].wichtig
    assert d2.vorgaenge["Insolvenz"].verlauf[0]["text"] == "Einladung erhalten"
    # unbekannte Felder (ältere/neuere Version) brechen nichts
    roh = d.als_dict()
    roh["fristen"][0]["unbekannt"] = 1
    assert Daten.aus_dict(roh).fristen[0].datum == "2026-12-09"


def test_gedaechtnis_ohne_4byte_emojis():
    d = Daten(zuletzt_verarbeitet="x")
    d.frist_hinzufuegen(Frist(datum="2026-12-09", was="Test 🔴 mit Emoji 📌"))
    text = gedaechtnis_text(d, [{"start": "2026-11-30T10:30:00+01:00", "titel": "Gespräch 🎉", "ort": "Erfurt", "offen": True}], JETZT)
    assert not any(ord(c) > 0xFFFF for c in text)
    assert "09.12.2026" in text and "Einladung noch nicht beantwortet" in text
    assert ohne_emoji("a🔴b") == "ab"


# --------------------------------------------------------------------------- Extraktion
def test_pruefen_verwirft_unsinnige_daten():
    e = extract.pruefen(antwort(fristen=[
        {"datum": "2026-12-09", "was": "Widerspruch einlegen", "errechnet": False},
        {"datum": "09.12.2026", "was": "Falsches Format", "errechnet": False},
        {"datum": "2031-01-01", "was": "Zu weit weg", "errechnet": False},
        {"datum": "2026-02-30", "was": "Gibt es nicht", "errechnet": False},
    ], termine=[{"datum": "2026-11-30", "uhrzeit": "10.30 Uhr", "titel": "Erstgespräch", "ort": "Erfurt"}]), HEUTE)
    assert [f["was"] for f in e.fristen] == ["Widerspruch einlegen"]
    assert "Falsches Format" in e.aufgaben  # ohne gültiges Datum -> Aufgabe, nicht verloren
    assert e.termine[0]["uhrzeit"] == "10:30"


def test_werbung_ist_nicht_relevant():
    e = extract.pruefen(antwort(kategorie="werbung", relevant=True), HEUTE)
    assert not e.relevant


def test_notizen_nur_bekannte_ids():
    llm = FakeLLM({"Neue Notizzeilen": {"erledigt_ids": ["abc", "erfunden"], "fristen": [], "aufgaben": [], "merken": []}})
    r = extract.notizen_auswerten(llm, ["Stromanbieter angerufen"], [{"id": "abc", "art": "frist", "was": "Stromanbieter"}], HEUTE)
    assert r["erledigt_ids"] == ["abc"]


def test_notiz_zeilen_nach_trenner():
    text = "Kopf\n- Beispiel 1\n---- Deine Einträge ab hier ----\n\n- Widerspruch abgeschickt\n-----\n• Bis 15.12. Steuer"
    assert notiz_zeilen(text) == ["Widerspruch abgeschickt", "Bis 15.12. Steuer"]


# --------------------------------------------------------------------------- Mailparsing
def test_html_und_pdf_mail():
    html = "<html><style>x{}</style><body><p>Hallo</p><p>Frist&nbsp;bis 9.12.</p></body></html>"
    n = {"payload": {"mimeType": "multipart/mixed", "parts": [
        {"mimeType": "text/html", "body": {"data": base64.urlsafe_b64encode(html.encode()).decode()}},
        {"mimeType": "application/pdf", "filename": "b.pdf", "body": {"attachmentId": "a1"}},
    ]}}
    r = mailparse.nachricht_zerlegen(n, lambda aid: b"kein pdf")
    assert "Hallo" in r["text"] and "Frist bis 9.12." in r["text"] and "x{}" not in r["text"]
    assert r["anhaenge"] == ""  # kaputtes PDF wird still übersprungen


# --------------------------------------------------------------------------- Kompletter Lauf
def test_kompletter_lauf():
    mails = [
        mail("m1", "Kündigungstermin vorgemerkt", "Bitte innerhalb von 14 Tagen anrufen."),
        mail("m2", "Black Friday!!!"),
        mail("m3", "Terminanfrage", "Passt Ihnen der 30.11. um 10:30?", von="Anne <anne@kanzlei.de>"),
        mail("m4", "Ihr Konto wird gesperrt", "Klicken Sie hier und geben Sie Ihr Passwort ein"),
        mail("m5", "Weitergeleitet von Outlook", "Antwort erbeten", an="m@live.de"),
        mail("m6", "Kaputte Antwort"),
    ]
    llm = FakeLLM({
        "Kündigungstermin": antwort(vorgang="Strom", rechtlich_oder_finanziell=True,
                                    fristen=[{"datum": "2026-12-09", "was": "Stromanbieter anrufen", "errechnet": True}]),
        "Terminanfrage": antwort(kategorie="termin", vorgang="Kanzlei", antwort_erwartet=True,
                                 termine=[{"datum": "2026-11-30", "uhrzeit": "10:30", "titel": "Erstgespräch", "ort": "Erfurt"}],
                                 personen=[{"name": "Anne", "rolle": "Kanzlei", "kontakt": "anne@kanzlei.de"}]),
        "Konto wird gesperrt": antwort(kategorie="auffaellig", verdacht="Phishing-Verdacht", antwort_erwartet=True),
        "Weitergeleitet": antwort(kategorie="aufgabe", antwort_erwartet=True, aufgaben=[{"was": "Antworten"}]),
        "Kaputte Antwort": LLMFehler("kein JSON"),
        "Neue Notizzeilen": {"erledigt_ids": [], "fristen": [{"datum": "2026-12-15", "was": "Steuer abgeben", "errechnet": False}],
                             "aufgaben": [], "merken": ["Mag kurze Briefings"]},
    })
    g = FakeGoogle(mails, notizen="---- Deine Einträge ab hier ----\nBis 15.12. Steuer abgeben")
    b = ausfuehren(cfg(), g, llm, JETZT)

    daten = json.loads(g.dateien[g.finden("Tagesbuddy – Daten.json")][1])
    fristen = {f["was"]: f for f in daten["fristen"]}
    assert set(fristen) == {"Stromanbieter anrufen", "Steuer abgeben"}
    assert fristen["Stromanbieter anrufen"]["kalender_id"] and fristen["Stromanbieter anrufen"]["errechnet"]
    # Kalender: 2 Fristen + 1 Termin-Erinnerung
    assert len(g.kalender) == 3 and any(k.get("uhrzeit") == "10:30" for k in g.kalender)
    # Entwurf nur für direkte Gmail-Mail ohne Phishing-Verdacht (nicht m4, nicht m5)
    assert [e[0] for e in g.entwuerfe] == ["m3"]
    # m6 schlug fehl -> nicht als verarbeitet markiert, Fehler im Briefing
    assert "m6" not in daten["verarbeitete_ids"] and "m1" in daten["verarbeitete_ids"]
    assert "Kaputte Antwort" in b.text
    # genau eine Mail, nur an mich
    assert len(g.gesendet) == 1
    betreff, html, text = g.gesendet[0]
    assert "Phishing-Verdacht" in html and "Stromanbieter anrufen" in html
    assert "Black Friday" not in html
    assert b.dringend == 1 and b.push.startswith("🔴")
    # Gedächtnis-Doc und Briefing-Archiv angelegt, ohne 4-Byte-Emojis
    ged = g.dateien[g.finden("Tagesbuddy – Gedächtnis")][1]
    assert "Stromanbieter anrufen" in ged and not any(ord(c) > 0xFFFF for c in ged)
    assert g.finden("Briefing 2026-11-27")
    assert daten["notizen_sekretaer"] == ["27.11. Mag kurze Briefings"]


def test_zweiter_lauf_keine_duplikate():
    """Am nächsten Tag: gleiche Mails/Notizen -> keine doppelten Fristen/Kalendereinträge."""
    llm = FakeLLM({"Kündigung": antwort(fristen=[{"datum": "2026-12-09", "was": "Stromanbieter anrufen", "errechnet": True}]),
                   "Neue Notizzeilen": {"erledigt_ids": [], "fristen": [], "aufgaben": [{"was": "Ordner sortieren"}], "merken": []}})
    g = FakeGoogle([mail("m1", "Kündigung")], notizen="Deine Einträge ab hier\nOrdner sortieren")
    ausfuehren(cfg(), g, llm, JETZT)
    n_llm = len(llm.anfragen)
    g.mails = [mail("m1", "Kündigung"), mail("m9", "Kündigung erneut")]
    ausfuehren(cfg(), g, llm, datetime(2026, 11, 28, 6, 35, tzinfo=TZ))
    daten = json.loads(g.dateien[g.finden("Tagesbuddy – Daten.json")][1])
    assert len(daten["fristen"]) == 1 and len(g.kalender) == 1
    assert len(daten["aufgaben"]) == 1
    assert len(llm.anfragen) == n_llm + 1  # nur m9 neu ausgewertet, Notiz nicht erneut
    assert g.seit.isoformat().startswith("2026-11-26T06:35")  # zuletzt verarbeitet - 1 Tag


def test_erledigt_ueber_notiz():
    start = Daten()
    f = start.frist_hinzufuegen(Frist(datum="2026-12-09", was="Stromanbieter anrufen", kalender_id="ev"))
    llm = FakeLLM({"Neue Notizzeilen": {"erledigt_ids": [f.id], "fristen": [], "aufgaben": [], "merken": []}})
    g = FakeGoogle([], notizen="Deine Einträge ab hier\nStromanbieter angerufen", daten=start.als_dict())
    b = ausfuehren(cfg(), g, llm, JETZT)
    daten = json.loads(g.dateien["d1"][1])
    assert daten["fristen"][0]["erledigt"] and "Stromanbieter anrufen" in b.text
    assert "Als erledigt markiert" in b.text


def test_trockenlauf_aendert_nichts():
    llm = FakeLLM({"Kündigung": antwort(fristen=[{"datum": "2026-12-09", "was": "anrufen", "errechnet": False}],
                                         antwort_erwartet=True)})
    g = FakeGoogle([mail("m1", "Kündigung")])
    vorher = dict(g.dateien)
    b = ausfuehren(cfg(), g, llm, JETZT, trocken=True)
    assert g.dateien == vorher and not g.gesendet and not g.kalender and not g.entwuerfe
    assert "anrufen" in b.text


def test_montag_wochenausblick():
    g = FakeGoogle([], termine=[{"start": "2026-12-03T18:30:00+01:00", "titel": "Linedance", "ort": "", "offen": False}])
    b = ausfuehren(cfg(), g, FakeLLM({}), datetime(2026, 11, 30, 6, 35, tzinfo=TZ))
    assert "DIESE WOCHE" in b.text and "Linedance" in b.text and "Diese Woche" in b.html


# --------------------------------------------------------------------------- Ollama-Client (echtes HTTP)
def test_ollama_client_gegen_fake_server():
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from tagesbuddy.llm import Ollama

    anfragen = []

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _json(self, obj):
            body = json.dumps(obj).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            self._json({"models": [{"name": "qwen2.5:14b-instruct"}]})

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            anfragen.append(body)
            inhalt = "kaputt{" if len(anfragen) == 1 else json.dumps({"gruss": "Hallo"})
            self._json({"message": {"content": inhalt}})

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        o = Ollama(f"http://127.0.0.1:{srv.server_port}", "qwen2.5:14b-instruct")
        o.pruefen()
        schema = {"type": "object", "properties": {"gruss": {"type": "string"}}}
        assert o.json("sys", "nutzer", schema) == {"gruss": "Hallo"}  # 1. Antwort kaputt -> Wiederholung
        assert anfragen[0]["format"] == schema and anfragen[0]["stream"] is False
        assert anfragen[0]["options"]["temperature"] == 0.1
        with pytest.raises(LLMFehler, match="ollama pull"):
            Ollama(f"http://127.0.0.1:{srv.server_port}", "llama3:70b").pruefen()
    finally:
        srv.shutdown()
    with pytest.raises(LLMFehler, match="nicht erreichbar"):
        Ollama("http://127.0.0.1:9", "x").pruefen()
