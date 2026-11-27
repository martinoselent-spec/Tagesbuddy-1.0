"""Konfiguration laden (config.toml im Ordner ``lokal``)."""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

BASIS = Path(__file__).resolve().parent.parent


@dataclass
class Config:
    email: str
    anrede: str = "Hallo"
    zeitzone: str = "Europe/Berlin"
    ollama_url: str = "http://localhost:11434"
    modell: str = "qwen2.5:14b-instruct"
    kontext: int = 8192
    timeout: int = 300
    ordner_id: str = ""
    gedaechtnis_titel: str = "Tagesbuddy – Gedächtnis"
    notizen_titel: str = "Tagesbuddy – Meine Notizen"
    daten_titel: str = "Tagesbuddy – Daten.json"
    briefings_ordner_titel: str = "Briefings"
    kalender_id: str = "primary"
    erster_lauf_tage: int = 14
    max_mails: int = 60
    entwuerfe: bool = True
    kalender_eintragen: bool = True
    ntfy_thema: str = ""
    ntfy_server: str = "https://ntfy.sh"
    basis: Path = field(default=BASIS)

    @property
    def credentials_pfad(self) -> Path:
        return self.basis / "credentials.json"

    @property
    def token_pfad(self) -> Path:
        return self.basis / "token.json"

    @property
    def log_pfad(self) -> Path:
        return self.basis / "logs"


def laden(pfad: Path | None = None) -> Config:
    pfad = pfad or BASIS / "config.toml"
    if not pfad.exists():
        raise SystemExit(
            f"Konfiguration fehlt: {pfad}\n"
            "Kopiere config.example.toml nach config.toml und trage deine Werte ein."
        )
    with pfad.open("rb") as f:
        d = tomllib.load(f)
    n, o, g = d.get("nutzer", {}), d.get("ollama", {}), d.get("google", {})
    v, p = d.get("verhalten", {}), d.get("push", {})
    email = n.get("email", "").strip()
    if not email or "@" not in email or email.startswith("dein.name"):
        raise SystemExit("Bitte in config.toml unter [nutzer] deine echte Gmail-Adresse eintragen.")
    return Config(
        email=email,
        anrede=n.get("anrede", "Hallo"),
        zeitzone=n.get("zeitzone", "Europe/Berlin"),
        ollama_url=o.get("url", "http://localhost:11434").rstrip("/"),
        modell=o.get("modell", "qwen2.5:14b-instruct"),
        kontext=int(o.get("kontext", 8192)),
        timeout=int(o.get("timeout_sekunden", 300)),
        ordner_id=g.get("ordner_id", ""),
        gedaechtnis_titel=g.get("gedaechtnis_titel", "Tagesbuddy – Gedächtnis"),
        notizen_titel=g.get("notizen_titel", "Tagesbuddy – Meine Notizen"),
        daten_titel=g.get("daten_titel", "Tagesbuddy – Daten.json"),
        briefings_ordner_titel=g.get("briefings_ordner_titel", "Briefings"),
        kalender_id=g.get("kalender_id", "primary"),
        erster_lauf_tage=int(v.get("erster_lauf_tage", 14)),
        max_mails=int(v.get("max_mails", 60)),
        entwuerfe=bool(v.get("entwuerfe", True)),
        kalender_eintragen=bool(v.get("kalender_eintragen", True)),
        ntfy_thema=p.get("ntfy_thema", ""),
        ntfy_server=p.get("ntfy_server", "https://ntfy.sh").rstrip("/"),
        basis=pfad.parent,
    )
