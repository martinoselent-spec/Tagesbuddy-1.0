"""Morgen-Briefing als HTML-Mail, Klartext und Drive-Archiv erzeugen."""
from __future__ import annotations

import html as h
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from .store import (BALD, DRINGEND, MONATE, WOCHENTAGE, Daten, in_tagen, ohne_emoji,
                    prioritaet, tage_bis, termin_zeile)


@dataclass
class Lauf:
    """Was in diesem Lauf passiert ist (für 'Was ich erledigt habe')."""
    gelesen: int = 0
    relevant: list[dict] = field(default_factory=list)   # {von, betreff, zusammenfassung, link, entwurf}
    auffaellig: list[str] = field(default_factory=list)
    neue_fristen: int = 0
    kalender: int = 0
    entwuerfe: int = 0
    notizen: int = 0
    erledigt: list[str] = field(default_factory=list)
    fehler: list[str] = field(default_factory=list)


@dataclass
class Briefing:
    betreff: str
    html: str
    text: str
    push: str
    dringend: int


def erstellen(daten: Daten, termine: list[dict], lauf: Lauf, jetzt: datetime, anrede: str,
              links: dict[str, str]) -> Briefing:
    heute = jetzt.date()
    offen = sorted((f for f in daten.fristen if not f.erledigt), key=lambda f: f.datum)
    fristen_14 = [f for f in offen if tage_bis(f.datum, heute) <= 14]
    termine_kurz = [t for t in termine if t["start"][:10] in (heute.isoformat(), (heute + timedelta(days=1)).isoformat())]
    offene_einladungen = [t for t in termine if t.get("offen")]

    wichtig: list[str] = []
    for f in fristen_14:
        if prioritaet(f, heute) == DRINGEND:
            wichtig.append(f"{f.was} – {in_tagen(tage_bis(f.datum, heute))} ({f.datum[8:10]}.{f.datum[5:7]}.)")
    for t in offene_einladungen[:2]:
        wichtig.append(f"Einladung noch nicht beantwortet: {termin_zeile(t)}")
    for t in termine_kurz:
        if t["start"][:10] == heute.isoformat() and len(t["start"]) > 10:
            wichtig.append(f"Heute: {termin_zeile(t)}")
    wichtig = wichtig[:3]

    abschnitte: list[tuple[str, str, list[str]]] = []  # (emoji, titel, zeilen)
    if wichtig:
        abschnitte.append(("🔴", "Wichtig", wichtig))
    if termine_kurz:
        abschnitte.append(("📅", "Termine heute & morgen", [termin_zeile(t) for t in termine_kurz]))
    if fristen_14:
        abschnitte.append(("⏰", "Fristen (nächste 14 Tage)", [
            f"{f.datum[8:10]}.{f.datum[5:7]}. ({in_tagen(tage_bis(f.datum, heute))}) {f.was}"
            + (f" – {f.vorgang}" if f.vorgang else "") for f in fristen_14]))
    if lauf.relevant:
        abschnitte.append(("✉️", "Neue Mails mit Handlungsbedarf", [
            f"{m['von_name']}: {m['betreff']} → {m['zusammenfassung']}" + ("  [Entwurf liegt bereit]" if m.get("entwurf") else "")
            for m in lauf.relevant[:8]]))
    aufg = [a.was for a in daten.aufgaben if not a.erledigt][:5]
    if aufg:
        abschnitte.append(("✅", "Offene Aufgaben", aufg))
    if heute.weekday() == 0:  # Montag: Wochenausblick
        woche = [termin_zeile(t) for t in termine if t["start"][:10] <= (heute + timedelta(days=6)).isoformat()]
        if woche:
            abschnitte.append(("🗓", "Diese Woche", woche[:10]))
    if lauf.auffaellig or lauf.fehler:
        abschnitte.append(("⚠️", "Auffällig", lauf.auffaellig + [f"Technik: {f}" for f in lauf.fehler]))
    erledigt = [f"{lauf.gelesen} neue Mails gelesen"]
    if lauf.kalender:
        erledigt.append(f"{lauf.kalender} Einträge im Kalender angelegt")
    if lauf.entwuerfe:
        erledigt.append(f"{lauf.entwuerfe} Antwort-Entwürfe angelegt (nicht gesendet)")
    if lauf.notizen:
        erledigt.append(f"{lauf.notizen} neue Notizen übernommen")
    erledigt += [f"Als erledigt markiert: {e}" for e in lauf.erledigt]
    erledigt.append("Gedächtnis aktualisiert")
    abschnitte.append(("🗂", "Was ich erledigt habe", erledigt))

    tag = f"{WOCHENTAGE[heute.weekday()]}, {heute.day}. {MONATE[heute.month - 1]}"
    n_dringend = sum(1 for f in fristen_14 if prioritaet(f, heute) == DRINGEND)
    betreff = f"☀️ Tagesbuddy {WOCHENTAGE[heute.weekday()][:2]}, {heute:%d.%m.}: {n_dringend} dringend, {len(fristen_14)} Fristen"

    # --- HTML ---
    teile = [f'<div style="font-family:Arial,Helvetica,sans-serif;font-size:15px;line-height:1.5;color:#222;max-width:600px">',
             f'<h2 style="margin:0 0 12px">☀️ {h.escape(anrede)}! {h.escape(tag)}</h2>']
    for emoji, titel, zeilen in abschnitte:
        farbe = "#c62828" if emoji == "🔴" else "#222"
        teile.append(f'<h3 style="color:{farbe};margin:16px 0 4px">{emoji} {h.escape(titel)}</h3><ul style="margin:0;padding-left:20px">')
        teile += [f"<li>{h.escape(z)}</li>" for z in zeilen]
        teile.append("</ul>")
    fuss = " · ".join(f'<a href="{h.escape(u)}">{h.escape(n)}</a>' for n, u in links.items() if u)
    teile.append(f'<p style="margin-top:20px;padding:10px;background:#f3f6fb;border-radius:6px">💡 Soll ich mir etwas merken? '
                 f'Schreib es in „Meine Notizen“ – ich lese es beim nächsten Lauf.</p>'
                 f'<p style="color:#999;font-size:12px">Tagesbuddy Lokal · {fuss} · '
                 f'Ausgewertet von deinem lokalen KI-Modell – Fristen bitte am Original prüfen. Dies ist keine Rechtsberatung.</p></div>')
    html = "\n".join(teile)

    # --- Klartext (auch für das Drive-Archiv, ohne 4-Byte-Emojis) ---
    text_z = [f"{anrede}! {tag}", ""]
    marker = {"🔴": DRINGEND, "⏰": "FRISTEN", "⚠️": "ACHTUNG"}
    for emoji, titel, zeilen in abschnitte:
        text_z.append(f"{marker.get(emoji, '')} {titel.upper()}".strip())
        text_z += [f"- {z}" for z in zeilen]
        text_z.append("")
    text_z.append("Keine Rechtsberatung. Fristen bitte am Original prüfen.")
    text = ohne_emoji("\n".join(text_z))

    if wichtig:
        push = "🔴 " + " · ".join(wichtig[:2])
    else:
        push = "☀️ Briefing ist da – heute nichts Dringendes."
    return Briefing(betreff=betreff, html=html, text=text, push=push[:240], dringend=n_dringend)


def von_name(von: str) -> str:
    name = von.split("<")[0].strip().strip('"')
    return name or von
