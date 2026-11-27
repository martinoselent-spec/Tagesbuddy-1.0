"""Gmail-Nachrichten in lesbaren Text umwandeln (inkl. PDF-Anhänge)."""
from __future__ import annotations

import base64
import io
import logging
import re
from email.utils import parseaddr

from bs4 import BeautifulSoup

log = logging.getLogger(__name__)


def b64(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def html_zu_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["style", "script", "head", "title"]):
        tag.decompose()
    for br in soup.find_all(["br", "p", "div", "tr", "li", "h1", "h2", "h3"]):
        br.append("\n")
    text = soup.get_text()
    text = re.sub(r"[ \t\xa0]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text.strip()


def pdf_zu_text(daten: bytes, max_seiten: int = 6) -> str:
    try:
        from pypdf import PdfReader
        r = PdfReader(io.BytesIO(daten))
        teile = [(s.extract_text() or "") for s in r.pages[:max_seiten]]
        return re.sub(r"\s+", " ", " ".join(teile)).strip()
    except Exception as e:  # beschädigte oder verschlüsselte PDFs
        log.info("PDF nicht lesbar: %s", e)
        return ""


def kopf(nachricht: dict, name: str) -> str:
    for h in nachricht.get("payload", {}).get("headers", []):
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


def teile_durchlaufen(teil: dict):
    yield teil
    for t in teil.get("parts", []) or []:
        yield from teile_durchlaufen(t)


def nachricht_zerlegen(nachricht: dict, anhang_laden=None) -> dict:
    """Gibt {text, pdf_anhaenge:[(name, attachment_id|bytes)]} zurück."""
    plain, html, pdfs = [], [], []
    for t in teile_durchlaufen(nachricht.get("payload", {})):
        mime = t.get("mimeType", "")
        body = t.get("body", {}) or {}
        name = t.get("filename", "")
        if name and (mime == "application/pdf" or name.lower().endswith(".pdf")):
            pdfs.append((name, body.get("attachmentId"), body.get("data")))
            continue
        if name:
            continue
        if mime == "text/plain" and body.get("data"):
            plain.append(b64(body["data"]).decode("utf-8", "replace"))
        elif mime == "text/html" and body.get("data"):
            html.append(b64(body["data"]).decode("utf-8", "replace"))
    text = "\n".join(plain).strip() or html_zu_text("\n".join(html))

    anhang_text = []
    for name, att_id, data in pdfs[:3]:
        roh = b64(data) if data else (anhang_laden(att_id) if (anhang_laden and att_id) else None)
        if roh and len(roh) < 8_000_000:
            inhalt = pdf_zu_text(roh)
            if inhalt:
                anhang_text.append(f"[{name}] {inhalt[:4000]}")
    return {"text": text, "anhaenge": "\n\n".join(anhang_text)}


def adresse(wert: str) -> str:
    return parseaddr(wert)[1].lower()
