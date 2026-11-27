"""Zugriff auf Gmail, Google Kalender und Google Drive über die offiziellen APIs.

Sicherheitsgrenzen sind hier fest eingebaut:
- Mails werden ausschließlich an die eigene Adresse aus config.toml gesendet.
- Antworten an Dritte gibt es nur als ENTWURF.
- Kalender: nur eigene Einträge ohne Teilnehmer, Titel mit "⏰ Frist:" / "📌 Erinnerung:".
- Es wird nichts gelöscht.
"""
from __future__ import annotations

import base64
import json
import logging
from datetime import date, datetime, timedelta
from email.message import EmailMessage

from .config import Config
from .mailparse import adresse, b64, kopf, nachricht_zerlegen

log = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",   # Entwürfe + Senden an sich selbst
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/drive",           # Gedächtnis + Notizen lesen/schreiben
]

FRIST_PREFIX = "⏰ Frist: "
ERINNERUNG_PREFIX = "📌 Erinnerung: "
DOC_MIME = "application/vnd.google-apps.document"
FOLDER_MIME = "application/vnd.google-apps.folder"


def anmelden(cfg: Config, interaktiv: bool = False):
    """Lädt token.json; mit interaktiv=True wird der Browser-Login gestartet."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    creds = None
    if cfg.token_pfad.exists():
        creds = Credentials.from_authorized_user_file(str(cfg.token_pfad), SCOPES)
    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            cfg.token_pfad.write_text(creds.to_json(), encoding="utf-8")
            return creds
        except Exception as e:
            log.warning("Token-Erneuerung fehlgeschlagen: %s", e)
    if not interaktiv:
        raise SystemExit(
            "Keine gültige Google-Anmeldung. Bitte einmal ausführen:  python -m tagesbuddy anmelden"
        )
    from google_auth_oauthlib.flow import InstalledAppFlow

    if not cfg.credentials_pfad.exists():
        raise SystemExit(f"credentials.json fehlt ({cfg.credentials_pfad}). Siehe Anleitung, Schritt 3.")
    flow = InstalledAppFlow.from_client_secrets_file(str(cfg.credentials_pfad), SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent")
    cfg.token_pfad.write_text(creds.to_json(), encoding="utf-8")
    return creds


class Google:
    def __init__(self, cfg: Config, creds):
        from googleapiclient.discovery import build

        self.cfg = cfg
        self.gmail = build("gmail", "v1", credentials=creds, cache_discovery=False)
        self.cal = build("calendar", "v3", credentials=creds, cache_discovery=False)
        self.drive = build("drive", "v3", credentials=creds, cache_discovery=False)

    # ===================================================================== Gmail
    def mails_seit(self, seit: datetime, maximal: int) -> list[dict]:
        q = f"in:inbox after:{int(seit.timestamp())} -category:promotions -category:social -from:me"
        ids, token = [], None
        while len(ids) < maximal:
            r = self.gmail.users().messages().list(userId="me", q=q, pageToken=token, maxResults=50).execute()
            ids += [m["id"] for m in r.get("messages", [])]
            token = r.get("nextPageToken")
            if not token:
                break
        mails = []
        for mid in ids[:maximal]:
            try:
                mails.append(self.mail_laden(mid))
            except Exception as e:
                log.warning("Mail %s nicht lesbar: %s", mid, e)
        return mails

    def mail_laden(self, mid: str) -> dict:
        n = self.gmail.users().messages().get(userId="me", id=mid, format="full").execute()

        def anhang(att_id: str) -> bytes:
            a = self.gmail.users().messages().attachments().get(userId="me", messageId=mid, id=att_id).execute()
            return b64(a["data"])

        teile = nachricht_zerlegen(n, anhang)
        an = kopf(n, "To") + " " + kopf(n, "Cc")
        ts = int(n.get("internalDate", "0")) / 1000
        return {
            "id": mid,
            "thread_id": n.get("threadId"),
            "von": kopf(n, "From"),
            "an": an.strip(),
            "betreff": kopf(n, "Subject"),
            "datum": datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M"),
            "message_id": kopf(n, "Message-ID"),
            # Nur direkt an Gmail adressierte Mails bekommen Entwürfe (nicht weitergeleitete Outlook-Mails).
            "an_mich": self.cfg.email.lower() in an.lower(),
            "link": f"https://mail.google.com/mail/u/0/#all/{n.get('threadId')}",
            **teile,
        }

    def an_mich_senden(self, betreff: str, html: str, text: str) -> None:
        msg = EmailMessage()
        msg["To"] = self.cfg.email          # fest: nur an den Nutzer selbst
        msg["From"] = self.cfg.email
        msg["Subject"] = betreff
        msg.set_content(text)
        msg.add_alternative(html, subtype="html")
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        self.gmail.users().messages().send(userId="me", body={"raw": raw}).execute()

    def entwurf_anlegen(self, mail: dict, text: str) -> str:
        msg = EmailMessage()
        msg["To"] = mail["von"]
        betreff = mail.get("betreff", "")
        msg["Subject"] = betreff if betreff.lower().startswith(("re:", "aw:")) else f"AW: {betreff}"
        if mail.get("message_id"):
            msg["In-Reply-To"] = mail["message_id"]
            msg["References"] = mail["message_id"]
        msg.set_content(text)
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        d = self.gmail.users().drafts().create(
            userId="me", body={"message": {"raw": raw, "threadId": mail.get("thread_id")}}
        ).execute()
        return d.get("id", "")

    # ================================================================== Kalender
    def termine(self, von: date, bis: date) -> list[dict]:
        r = self.cal.events().list(
            calendarId=self.cfg.kalender_id, timeMin=f"{von.isoformat()}T00:00:00Z",
            timeMax=f"{bis.isoformat()}T23:59:59Z", singleEvents=True, orderBy="startTime",
            timeZone=self.cfg.zeitzone, maxResults=100,
        ).execute()
        out = []
        for e in r.get("items", []):
            ich = next((a for a in e.get("attendees", []) if a.get("self")), None)
            out.append({
                "id": e.get("id"),
                "titel": e.get("summary", "(ohne Titel)"),
                "start": e.get("start", {}).get("dateTime") or e.get("start", {}).get("date", ""),
                "ort": e.get("location", ""),
                "offen": bool(ich and ich.get("responseStatus") == "needsAction"),
            })
        return out

    def _eintraege_am(self, tag: date) -> list[dict]:
        r = self.cal.events().list(
            calendarId=self.cfg.kalender_id, timeMin=f"{tag.isoformat()}T00:00:00Z",
            timeMax=f"{(tag + timedelta(days=1)).isoformat()}T23:59:59Z", singleEvents=True, maxResults=50,
        ).execute()
        return r.get("items", [])

    def eintrag_suchen(self, tag: date, text: str) -> str | None:
        from .store import aehnlich
        for e in self._eintraege_am(tag):
            titel = e.get("summary", "")
            if aehnlich(titel.replace(FRIST_PREFIX, "").replace(ERINNERUNG_PREFIX, ""), text, 0.5):
                return e.get("id")
        return None

    def frist_eintragen(self, datum: str, was: str, beschreibung: str, wichtig: bool) -> str:
        tag = date.fromisoformat(datum)
        erinnerungen = [{"method": "popup", "minutes": 4320}, {"method": "email", "minutes": 4320},
                        {"method": "popup", "minutes": 1440}]
        if wichtig:
            erinnerungen += [{"method": "popup", "minutes": 10080}, {"method": "email", "minutes": 10080}]
        body = {
            "summary": FRIST_PREFIX + was[:150],
            "description": beschreibung + "\n– angelegt von Tagesbuddy Lokal",
            "start": {"date": tag.isoformat()},
            "end": {"date": (tag + timedelta(days=1)).isoformat()},
            "transparency": "transparent",
            "reminders": {"useDefault": False, "overrides": erinnerungen[:5]},
        }
        return self.cal.events().insert(calendarId=self.cfg.kalender_id, body=body).execute()["id"]

    def erinnerung_eintragen(self, datum: str, uhrzeit: str, titel: str, ort: str, beschreibung: str) -> str:
        if uhrzeit:
            start = datetime.fromisoformat(f"{datum}T{uhrzeit}:00")
            body_zeit = {
                "start": {"dateTime": start.isoformat(), "timeZone": self.cfg.zeitzone},
                "end": {"dateTime": (start + timedelta(hours=1)).isoformat(), "timeZone": self.cfg.zeitzone},
            }
        else:
            tag = date.fromisoformat(datum)
            body_zeit = {"start": {"date": tag.isoformat()}, "end": {"date": (tag + timedelta(days=1)).isoformat()}}
        body = {
            "summary": ERINNERUNG_PREFIX + titel[:150],
            "location": ort,
            "description": beschreibung + "\n– angelegt von Tagesbuddy Lokal",
            "reminders": {"useDefault": False, "overrides": [{"method": "popup", "minutes": 1440},
                                                              {"method": "popup", "minutes": 120}]},
            **body_zeit,
        }
        return self.cal.events().insert(calendarId=self.cfg.kalender_id, body=body).execute()["id"]

    # ===================================================================== Drive
    def finden(self, titel: str, eltern: str | None = None, mime: str | None = None) -> str | None:
        t = titel.replace("\\", "\\\\").replace("'", "\\'")
        q = f"name = '{t}' and trashed = false"
        if eltern:
            q += f" and '{eltern}' in parents"
        if mime:
            q += f" and mimeType = '{mime}'"
        r = self.drive.files().list(q=q, orderBy="modifiedTime desc", pageSize=5, fields="files(id,name)").execute()
        f = r.get("files", [])
        return f[0]["id"] if f else None

    def ordner(self, titel: str, eltern: str | None = None) -> str:
        fid = self.finden(titel, eltern, FOLDER_MIME)
        if fid:
            return fid
        body = {"name": titel, "mimeType": FOLDER_MIME, **({"parents": [eltern]} if eltern else {})}
        return self.drive.files().create(body=body, fields="id").execute()["id"]

    def text_lesen(self, fid: str) -> str:
        meta = self.drive.files().get(fileId=fid, fields="mimeType").execute()
        if meta["mimeType"].startswith("application/vnd.google-apps"):
            daten = self.drive.files().export(fileId=fid, mimeType="text/plain").execute()
        else:
            daten = self.drive.files().get_media(fileId=fid).execute()
        return daten.decode("utf-8-sig") if isinstance(daten, bytes) else str(daten)

    def text_schreiben(self, titel: str, eltern: str, text: str, als_doc: bool, fid: str | None = None) -> str:
        """Datei anlegen oder Inhalt ersetzen (gleiche ID bleibt erhalten)."""
        from googleapiclient.http import MediaInMemoryUpload

        mime = "text/plain" if als_doc else ("application/json" if titel.endswith(".json") else "text/plain")
        media = MediaInMemoryUpload(text.encode("utf-8"), mimetype=mime, resumable=False)
        if fid:
            return self.drive.files().update(fileId=fid, media_body=media, fields="id").execute()["id"]
        body = {"name": titel, "parents": [eltern]}
        if als_doc:
            body["mimeType"] = DOC_MIME
        return self.drive.files().create(body=body, media_body=media, fields="id").execute()["id"]

    def json_lesen(self, fid: str) -> dict:
        return json.loads(self.text_lesen(fid) or "{}")
