"""Schlanker Client für Ollama mit strukturierter JSON-Ausgabe."""
from __future__ import annotations

import json
import logging
from typing import Any, Protocol

import requests

log = logging.getLogger(__name__)


class LLMFehler(RuntimeError):
    pass


class LLM(Protocol):
    def json(self, system: str, nutzer: str, schema: dict) -> dict: ...
    def text(self, system: str, nutzer: str) -> str: ...


class Ollama:
    def __init__(self, url: str, modell: str, kontext: int = 8192, timeout: int = 300):
        self.url, self.modell, self.kontext, self.timeout = url.rstrip("/"), modell, kontext, timeout

    # -- Prüfung -----------------------------------------------------------
    def pruefen(self) -> None:
        """Wirft LLMFehler mit verständlicher Meldung, wenn Ollama/Modell fehlt."""
        try:
            r = requests.get(f"{self.url}/api/tags", timeout=10)
            r.raise_for_status()
        except requests.RequestException as e:
            raise LLMFehler(
                f"Ollama unter {self.url} nicht erreichbar ({e}). Läuft Ollama? "
                "Bei Zugriff über Tailscale: OLLAMA_HOST=0.0.0.0 setzen."
            ) from e
        namen = {m.get("name", "") for m in r.json().get("models", [])}
        basis = {n.split(":")[0] for n in namen}
        if self.modell not in namen and self.modell.split(":")[0] not in basis:
            raise LLMFehler(
                f"Modell '{self.modell}' ist nicht installiert. "
                f"Installieren mit:  ollama pull {self.modell}"
            )

    # -- Anfragen ----------------------------------------------------------
    def _chat(self, system: str, nutzer: str, fmt: Any = None) -> str:
        body: dict[str, Any] = {
            "model": self.modell,
            "stream": False,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": nutzer},
            ],
            "options": {"temperature": 0.1, "num_ctx": self.kontext},
        }
        if fmt is not None:
            body["format"] = fmt
        try:
            r = requests.post(f"{self.url}/api/chat", json=body, timeout=self.timeout)
            r.raise_for_status()
        except requests.RequestException as e:
            raise LLMFehler(f"Ollama-Anfrage fehlgeschlagen: {e}") from e
        return r.json().get("message", {}).get("content", "")

    def json(self, system: str, nutzer: str, schema: dict) -> dict:
        letzter = ""
        for versuch in range(3):
            antwort = self._chat(system, nutzer, fmt=schema)
            try:
                daten = json.loads(antwort)
                if isinstance(daten, dict):
                    return daten
            except json.JSONDecodeError:
                pass
            letzter = antwort[:300]
            log.warning("Ungültiges JSON vom Modell (Versuch %d): %s", versuch + 1, letzter)
        raise LLMFehler(f"Modell lieferte kein gültiges JSON: {letzter}")

    def text(self, system: str, nutzer: str) -> str:
        return self._chat(system, nutzer).strip()
