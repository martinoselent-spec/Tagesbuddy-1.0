"""Strukturiertes Gedächtnis: Fristen, Aufgaben, Vorgänge, Personen.

Das LLM liefert nur Rohdaten; Zusammenführen, Duplikaterkennung, Priorität und
Darstellung erledigt dieser deterministische Code. Gespeichert wird als JSON in
Google Drive ("Tagesbuddy – Daten.json"), daraus wird das lesbare
Gedächtnis-Dokument erzeugt.
"""
from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import date, datetime

DRINGEND, BALD, SPAETER = "[DRINGEND]", "[BALD]", "[SPÄTER]"

_STOPP = set(
    "der die das und oder ein eine einen einem einer zu zum zur von vom mit für fuer auf an am im in "
    "bis bei beim ist sind wird werden nicht noch bitte frist aufgabe ihr ihre ihren sie".split()
)

# 4-Byte-Zeichen (Emojis) werden beim Upload in Google Docs zu Zeichensalat.
_ASTRAL = re.compile(r"[\U00010000-\U0010FFFF]")


def ohne_emoji(text: str) -> str:
    return _ASTRAL.sub("", text).replace("  ", " ")


def _woerter(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-zäöüß0-9]+", text.lower()) if len(w) > 2 and w not in _STOPP}


def aehnlich(a: str, b: str, schwelle: float = 0.5) -> bool:
    wa, wb = _woerter(a), _woerter(b)
    if not wa or not wb:
        return a.strip().lower() == b.strip().lower()
    return len(wa & wb) / min(len(wa), len(wb)) >= schwelle


def neue_id() -> str:
    return uuid.uuid4().hex[:10]


def hash_zeile(zeile: str) -> str:
    return hashlib.sha1(zeile.strip().lower().encode()).hexdigest()[:16]


@dataclass
class Frist:
    datum: str  # YYYY-MM-DD
    was: str
    vorgang: str = ""
    quelle: str = ""
    errechnet: bool = False
    wichtig: bool = False  # rechtlich oder finanziell relevant
    kalender_id: str = ""
    erledigt: bool = False
    erledigt_am: str = ""
    id: str = field(default_factory=neue_id)


@dataclass
class Aufgabe:
    was: str
    vorgang: str = ""
    quelle: str = ""
    seit: str = ""
    erledigt: bool = False
    erledigt_am: str = ""
    id: str = field(default_factory=neue_id)


@dataclass
class Person:
    name: str
    rolle: str = ""
    kontakt: str = ""
    vorgang: str = ""


@dataclass
class Vorgang:
    beschreibung: str = ""
    verlauf: list[dict] = field(default_factory=list)  # {"datum": ..., "text": ...}
    naechster_schritt: str = ""


@dataclass
class Daten:
    zuletzt_verarbeitet: str = ""
    verarbeitete_ids: list[str] = field(default_factory=list)
    notizen_hashes: list[str] = field(default_factory=list)
    fristen: list[Frist] = field(default_factory=list)
    aufgaben: list[Aufgabe] = field(default_factory=list)
    vorgaenge: dict[str, Vorgang] = field(default_factory=dict)
    personen: list[Person] = field(default_factory=list)
    notizen_sekretaer: list[str] = field(default_factory=list)
    version: int = 1

    # -- (De-)Serialisierung ---------------------------------------------------
    @classmethod
    def aus_dict(cls, d: dict) -> "Daten":
        if not d:
            return cls()

        def nur(klasse, x):
            erlaubt = klasse.__dataclass_fields__.keys()
            return klasse(**{k: v for k, v in x.items() if k in erlaubt})

        return cls(
            zuletzt_verarbeitet=d.get("zuletzt_verarbeitet", ""),
            verarbeitete_ids=list(d.get("verarbeitete_ids", [])),
            notizen_hashes=list(d.get("notizen_hashes", [])),
            fristen=[nur(Frist, x) for x in d.get("fristen", [])],
            aufgaben=[nur(Aufgabe, x) for x in d.get("aufgaben", [])],
            vorgaenge={k: nur(Vorgang, v) for k, v in d.get("vorgaenge", {}).items()},
            personen=[nur(Person, x) for x in d.get("personen", [])],
            notizen_sekretaer=list(d.get("notizen_sekretaer", [])),
            version=d.get("version", 1),
        )

    def als_dict(self) -> dict:
        d = asdict(self)
        d["verarbeitete_ids"] = self.verarbeitete_ids[-3000:]
        d["notizen_hashes"] = self.notizen_hashes[-3000:]
        return d

    # -- Hinzufügen mit Duplikaterkennung -----------------------------------------
    def frist_hinzufuegen(self, f: Frist) -> Frist | None:
        """Gibt die neue Frist zurück oder None, wenn sie schon bekannt war."""
        for alt in self.fristen:
            if alt.datum == f.datum and (aehnlich(alt.was, f.was) or (f.vorgang and alt.vorgang == f.vorgang and aehnlich(alt.was, f.was, 0.3))):
                alt.wichtig = alt.wichtig or f.wichtig
                return None
        self.fristen.append(f)
        return f

    def aufgabe_hinzufuegen(self, a: Aufgabe) -> Aufgabe | None:
        for alt in self.aufgaben:
            if not alt.erledigt and aehnlich(alt.was, a.was, 0.6):
                return None
        self.aufgaben.append(a)
        return a

    def person_hinzufuegen(self, p: Person) -> None:
        if not p.name.strip():
            return
        for alt in self.personen:
            if alt.name.lower() == p.name.lower():
                alt.rolle = alt.rolle or p.rolle
                alt.kontakt = alt.kontakt or p.kontakt
                alt.vorgang = alt.vorgang or p.vorgang
                return
        self.personen.append(p)

    def verlauf_eintragen(self, vorgang: str, datum: str, text: str, beschreibung: str = "") -> None:
        if not vorgang:
            return
        v = self.vorgaenge.setdefault(vorgang, Vorgang())
        if beschreibung and not v.beschreibung:
            v.beschreibung = beschreibung
        if not any(e.get("datum") == datum and aehnlich(e.get("text", ""), text, 0.7) for e in v.verlauf):
            v.verlauf.append({"datum": datum, "text": text})
            v.verlauf = v.verlauf[-25:]

    def erledigen(self, ids: list[str], heute: date) -> list[str]:
        erledigt = []
        for x in [*self.fristen, *self.aufgaben]:
            if x.id in ids and not x.erledigt:
                x.erledigt, x.erledigt_am = True, heute.isoformat()
                erledigt.append(x.was)
        return erledigt

    def offene(self) -> list[dict]:
        """Kompakte Liste offener Punkte (für das LLM beim Abgleich von Notizen)."""
        out = [{"id": f.id, "art": "frist", "datum": f.datum, "was": f.was} for f in self.fristen if not f.erledigt]
        out += [{"id": a.id, "art": "aufgabe", "was": a.was} for a in self.aufgaben if not a.erledigt]
        return out

    def aufraeumen(self, heute: date) -> None:
        """Erledigtes, das älter als 30 Tage ist, entfernen."""
        def frisch(x) -> bool:
            if not x.erledigt or not x.erledigt_am:
                return True
            return (heute - date.fromisoformat(x.erledigt_am)).days <= 30
        self.fristen = [f for f in self.fristen if frisch(f)]
        self.aufgaben = [a for a in self.aufgaben if frisch(a)]


# -- Priorität -----------------------------------------------------------------------
def tage_bis(datum: str, heute: date) -> int:
    return (date.fromisoformat(datum) - heute).days


def prioritaet(f: Frist, heute: date) -> str:
    t = tage_bis(f.datum, heute)
    if t <= 1 or (f.wichtig and t <= 14):
        return DRINGEND
    if t <= 7:
        return BALD
    return SPAETER


def in_tagen(t: int) -> str:
    if t < 0:
        return f"seit {-t} Tag{'en' if t < -1 else ''} überfällig"
    return {0: "heute", 1: "morgen"}.get(t, f"in {t} Tagen")


def datum_de(iso: str) -> str:
    d = date.fromisoformat(iso[:10])
    return d.strftime("%d.%m.%Y")


WOCHENTAGE = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
MONATE = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August",
          "September", "Oktober", "November", "Dezember"]


# -- Gedächtnis-Dokument ------------------------------------------------------------------
def gedaechtnis_text(daten: Daten, termine: list[dict], jetzt: datetime) -> str:
    heute = jetzt.date()
    z: list[str] = [
        "Tagesbuddy – Gedächtnis",
        f"Stand: {jetzt:%d.%m.%Y %H:%M}  ·  Zuletzt verarbeitet: {daten.zuletzt_verarbeitet}",
        "Erstellt von Tagesbuddy Lokal. Nicht von Hand ändern – Ergänzungen bitte in „Meine Notizen“.",
        f"Prioritäten: {DRINGEND} heute/morgen oder rechtlich/finanziell wichtig · {BALD} 7 Tage · {SPAETER} später",
        "",
        "1. FRISTEN (nach Datum sortiert)",
    ]
    offen = sorted((f for f in daten.fristen if not f.erledigt), key=lambda f: f.datum)
    for f in offen:
        t = tage_bis(f.datum, heute)
        teile = [f"- [ ] {datum_de(f.datum)} {prioritaet(f, heute)} {f.was}"]
        if f.errechnet:
            teile.append("(errechnet)")
        teile.append(f"– {in_tagen(t)}")
        if f.vorgang:
            teile.append(f"– Vorgang: {f.vorgang}")
        if f.quelle:
            teile.append(f"– Quelle: {f.quelle}")
        teile.append(f"– Kalender: {'ja' if f.kalender_id else 'nein'}")
        z.append(" ".join(teile))
    if not offen:
        z.append("- (keine offenen Fristen)")

    z += ["", "2. OFFENE AUFGABEN"]
    offene_aufg = [a for a in daten.aufgaben if not a.erledigt]
    for a in offene_aufg:
        extra = f" – Vorgang: {a.vorgang}" if a.vorgang else ""
        seit = f" – seit {datum_de(a.seit)}" if a.seit else ""
        z.append(f"- [ ] {a.was}{extra}{seit}")
    if not offene_aufg:
        z.append("- (keine offenen Aufgaben)")

    z += ["", "3. KOMMENDE TERMINE (14 Tage)"]
    for t in termine:
        z.append(f"- {termin_zeile(t)}")
    if not termine:
        z.append("- (keine Termine)")

    z += ["", "4. VORGÄNGE"]
    for name, v in sorted(daten.vorgaenge.items()):
        z.append(f"## {name}")
        if v.beschreibung:
            z.append(f"- Worum es geht: {v.beschreibung}")
        if v.verlauf:
            z.append("- Verlauf: " + " · ".join(f"{datum_de(e['datum'])} {e['text']}" for e in v.verlauf[-10:]))
        if v.naechster_schritt:
            z.append(f"- Nächster Schritt: {v.naechster_schritt}")
        z.append("")

    z += ["5. PERSONEN & KONTAKTE"]
    for p in daten.personen:
        z.append(" – ".join(x for x in [f"- {p.name}", p.rolle, p.kontakt, (f"Vorgang: {p.vorgang}" if p.vorgang else "")] if x))

    z += ["", "6. ERLEDIGT (letzte 30 Tage)"]
    erl = [x for x in [*daten.fristen, *daten.aufgaben] if x.erledigt]
    for x in sorted(erl, key=lambda x: x.erledigt_am, reverse=True):
        z.append(f"- [x] {datum_de(x.erledigt_am)} {x.was}")

    z += ["", "7. NOTIZEN DES SEKRETÄRS"]
    z += [f"- {n}" for n in daten.notizen_sekretaer[-15:]]
    return ohne_emoji("\n".join(z)) + "\n"


def termin_zeile(t: dict) -> str:
    start = t.get("start", "")
    if len(start) > 10:
        dt = datetime.fromisoformat(start)
        wann = f"{WOCHENTAGE[dt.weekday()][:2]} {dt:%d.%m. %H:%M}"
    else:
        d = date.fromisoformat(start)
        wann = f"{WOCHENTAGE[d.weekday()][:2]} {d:%d.%m.} ganztägig"
    teile = [wann, t.get("titel", "")]
    if t.get("ort"):
        teile.append(f"({t['ort']})")
    if t.get("offen"):
        teile.append("– Einladung noch nicht beantwortet")
    return " ".join(teile)
