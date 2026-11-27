"""Optionale Push-Nachricht über ntfy (https://ntfy.sh)."""
from __future__ import annotations

import logging

import requests

log = logging.getLogger(__name__)


def push(server: str, thema: str, titel: str, text: str, dringend: bool = False) -> None:
    if not thema:
        return
    try:
        # JSON-Veröffentlichung: Umlaute und Emojis funktionieren auch im Titel.
        requests.post(
            server,
            json={"topic": thema, "title": titel, "message": text, "priority": 4 if dringend else 3},
            timeout=15,
        ).raise_for_status()
    except requests.RequestException as e:
        log.warning("Push fehlgeschlagen: %s", e)
