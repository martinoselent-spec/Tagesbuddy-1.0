"""Befehle:

    python -m tagesbuddy anmelden      Einmalig: Google-Login im Browser
    python -m tagesbuddy pruefen       Ollama, Modell und Google-Zugriff testen
    python -m tagesbuddy lauf          Briefing jetzt erstellen und senden
    python -m tagesbuddy lauf --trocken  Alles auswerten, aber nichts ändern/senden
"""
from __future__ import annotations

import argparse
import logging
import sys
import traceback
from datetime import datetime
from logging.handlers import RotatingFileHandler
from zoneinfo import ZoneInfo

from . import config as config_mod
from .llm import LLMFehler, Ollama


def _logging(cfg) -> None:
    cfg.log_pfad.mkdir(exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    datei = RotatingFileHandler(cfg.log_pfad / "tagesbuddy.log", maxBytes=1_000_000, backupCount=5, encoding="utf-8")
    datei.setFormatter(fmt)
    konsole = logging.StreamHandler(sys.stdout)
    konsole.setFormatter(fmt)
    logging.basicConfig(level=logging.INFO, handlers=[datei, konsole])
    for laut in ("googleapiclient", "urllib3", "google_auth_oauthlib"):
        logging.getLogger(laut).setLevel(logging.WARNING)


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # Windows-Konsole: Umlaute/Emojis
    p = argparse.ArgumentParser(prog="tagesbuddy", description="Tagesbuddy Lokal – digitaler Sekretär mit Ollama")
    sub = p.add_subparsers(dest="befehl", required=True)
    sub.add_parser("anmelden", help="Google-Login (einmalig)")
    sub.add_parser("pruefen", help="Verbindungen testen")
    l = sub.add_parser("lauf", help="Briefing erstellen")
    l.add_argument("--trocken", action="store_true", help="nichts ändern, nichts senden; Briefing anzeigen")
    args = p.parse_args(argv)

    cfg = config_mod.laden()
    _logging(cfg)
    log = logging.getLogger("tagesbuddy")
    from .google_api import Google, anmelden

    if args.befehl == "anmelden":
        anmelden(cfg, interaktiv=True)
        print("✓ Google-Anmeldung gespeichert (token.json).")
        return 0

    llm = Ollama(cfg.ollama_url, cfg.modell, cfg.kontext, cfg.timeout)

    if args.befehl == "pruefen":
        ok = True
        try:
            llm.pruefen()
            antwort = llm.json("Antworte als JSON.", "Sag hallo auf Deutsch.",
                               {"type": "object", "properties": {"gruss": {"type": "string"}}, "required": ["gruss"]})
            print(f"✓ Ollama + Modell {cfg.modell}: {antwort.get('gruss')}")
        except LLMFehler as e:
            ok = False
            print(f"✗ {e}")
        try:
            g = Google(cfg, anmelden(cfg))
            profil = g.gmail.users().getProfile(userId="me").execute()
            print(f"✓ Gmail: {profil.get('emailAddress')} ({profil.get('messagesTotal')} Nachrichten)")
            g.termine(datetime.now().date(), datetime.now().date())
            print("✓ Google Kalender lesbar")
            ordner = cfg.ordner_id or g.finden("Tagesbuddy", mime="application/vnd.google-apps.folder")
            print(f"✓ Drive-Ordner Tagesbuddy: {ordner or 'wird beim ersten Lauf angelegt'}")
            if profil.get("emailAddress", "").lower() != cfg.email.lower():
                ok = False
                print(f"✗ Angemeldetes Konto ({profil.get('emailAddress')}) ≠ config.toml ({cfg.email})")
        except SystemExit as e:
            ok = False
            print(f"✗ {e}")
        except Exception as e:
            ok = False
            print(f"✗ Google: {e}")
        return 0 if ok else 1

    # --- lauf ---
    jetzt = datetime.now(ZoneInfo(cfg.zeitzone))
    google = None
    try:
        llm.pruefen()
        google = Google(cfg, anmelden(cfg))
        from .run import ausfuehren
        b = ausfuehren(cfg, google, llm, jetzt, trocken=args.trocken)
        print("\n" + b.betreff + "\n\n" + b.text)
        log.info("Lauf fertig: %s", b.betreff)
        return 0
    except Exception as e:
        log.error("Lauf abgebrochen: %s\n%s", e, traceback.format_exc())
        if google is None and not isinstance(e, LLMFehler):
            return 1
        try:  # Fehler-Mail an sich selbst, damit ein Ausfall nicht unbemerkt bleibt
            google = google or Google(cfg, anmelden(cfg))
            google.an_mich_senden("⚠️ Tagesbuddy: Lauf fehlgeschlagen",
                                  f"<p>Der heutige Lauf ist abgebrochen:</p><pre>{e}</pre>"
                                  f"<p>Details: logs/tagesbuddy.log auf dem PC.</p>",
                                  f"Der heutige Lauf ist abgebrochen: {e}\nDetails: logs/tagesbuddy.log")
        except Exception:
            log.exception("Auch die Fehler-Mail konnte nicht gesendet werden")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
