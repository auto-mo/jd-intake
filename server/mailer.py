"""Email for jd-intake: send approved outreach over SMTP, read mail over IMAP. Standard library only.

Three jobs, and nothing else:
  send()          one approved cold email (or its approved follow-up), with the resume attached.
  fetch()         mail you received (or, with sent=True, mail you sent) in the last N days, read only.
  find_bounces()  delivery failures in the inbox, read only.

The rules this file keeps:
  - Only approved cold outreach is ever sent. app.py calls send() from the send queue and nowhere else;
    there is no function here that answers, forwards or replies to a message someone else sent you.
    A follow-up threads under your OWN earlier email (In-Reply-To is that email's Message-ID).
  - Reading never changes the mailbox. Folders are opened read only (EXAMINE) and bodies are fetched
    with BODY.PEEK, so nothing is marked read, moved, flagged or deleted.

Settings come from .env (see .env.example and docs/email.md):
  MAIL_ADDRESS, MAIL_PASSWORD             the account (an app password, not your login password)
  SMTP_HOST, SMTP_PORT                    465 = SSL, anything else = STARTTLS
  IMAP_HOST, IMAP_PORT                    usually 993
  MAIL_SENT_FOLDER                        where your sent mail lives, e.g. "[Gmail]/Sent Mail" or "Sent"
  MAIL_INBOX_FOLDER (optional)            default INBOX
  MAIL_SAVE_SENT (optional, true/false)   also file a copy of each sent email in MAIL_SENT_FOLDER, for
                                          providers whose SMTP does not do it (Gmail and Outlook do)

The shapes returned are the ones app.py consumes:
  send()         -> {"id": "<message id without angle brackets>"}
  fetch()        -> [{"id", "thread_id", "date" (ISO 8601), "from_address", "from_name", "to", "subject", "text"}]
  find_bounces() -> [{"recipient", "code", "status", "reason", "permanent", "date"}]
"""
import email
import email.policy
import imaplib
import mimetypes
import os
import re
import smtplib
import ssl
import time
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import formataddr, make_msgid, parseaddr, parsedate_to_datetime

REQUIRED_SEND = ("MAIL_ADDRESS", "MAIL_PASSWORD", "SMTP_HOST")
REQUIRED_READ = ("MAIL_ADDRESS", "MAIL_PASSWORD", "IMAP_HOST")
MAX_MESSAGES = 500          # per fetch; the newest are kept
TIMEOUT = 60


class MailError(RuntimeError):
    pass


def missing(env, read=False):
    """The .env keys that are still empty for sending (or, with read=True, for reading)."""
    return [k for k in (REQUIRED_READ if read else REQUIRED_SEND) if not (env.get(k) or "").strip()]


def _need(env, read=False):
    gap = missing(env, read)
    if gap:
        raise MailError("Email is not set up: add " + ", ".join(gap) + " to .env (docs/email.md)")


def _bool(v):
    return str(v or "").strip().lower() in ("1", "true", "yes", "on")


# ── sending ──────────────────────────────────────────────────────────────────

def build_message(env, to, subject, body, attachment=None, in_reply_to=None, from_name=""):
    """The EmailMessage for one approved email. `attachment` is a file path; `in_reply_to` is the
    Message-ID (without brackets) of your own earlier email, for a follow-up in the same thread."""
    addr = env["MAIL_ADDRESS"].strip()
    msg = EmailMessage(policy=email.policy.SMTP)
    msg["From"] = formataddr((from_name, addr)) if from_name else addr
    msg["To"] = to
    msg["Subject"] = subject or ""
    msg["Date"] = email.utils.formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=addr.rpartition("@")[2] or None)
    if in_reply_to:
        ref = "<" + in_reply_to.strip("<>") + ">"
        msg["In-Reply-To"] = ref
        msg["References"] = ref
    msg.set_content(body or "")
    if attachment:
        ctype, _ = mimetypes.guess_type(attachment)
        maintype, subtype = (ctype or "application/octet-stream").split("/", 1)
        with open(attachment, "rb") as f:
            msg.add_attachment(f.read(), maintype=maintype, subtype=subtype, filename=os.path.basename(attachment))
    return msg


def send(env, to, subject, body, attachment=None, in_reply_to=None, from_name=""):
    """Send one approved email. Returns {"id": message id}. Raises on any failure, so the caller marks
    the message failed and nothing is retried behind your back."""
    _need(env)
    if not to or "@" not in to:
        raise MailError("no recipient address")
    msg = build_message(env, to, subject, body, attachment, in_reply_to, from_name)
    host, port = env["SMTP_HOST"].strip(), int(env.get("SMTP_PORT") or 587)
    ctx = ssl.create_default_context()
    if port == 465:
        server = smtplib.SMTP_SSL(host, port, timeout=TIMEOUT, context=ctx)
    else:
        server = smtplib.SMTP(host, port, timeout=TIMEOUT)
    try:
        if port != 465:
            server.starttls(context=ctx)
        server.login(env["MAIL_ADDRESS"].strip(), env["MAIL_PASSWORD"])
        server.send_message(msg)
    finally:
        try:
            server.quit()
        except Exception:  # noqa: BLE001
            pass
    if _bool(env.get("MAIL_SAVE_SENT")) and not missing(env, read=True) and env.get("MAIL_SENT_FOLDER"):
        try:
            with _imap(env) as im:
                im.append(_folder(env["MAIL_SENT_FOLDER"]), "\\Seen", imaplib.Time2Internaldate(time.time()),
                          msg.as_bytes())
        except Exception:  # noqa: BLE001
            pass        # the email went out; a missing copy in Sent is not a reason to report a failure
    return {"id": msg["Message-ID"].strip().strip("<>")}


# ── reading (read only) ──────────────────────────────────────────────────────

class _imap:
    def __init__(self, env):
        self.env = env

    def __enter__(self):
        _need(self.env, read=True)
        host, port = self.env["IMAP_HOST"].strip(), int(self.env.get("IMAP_PORT") or 993)
        self.im = imaplib.IMAP4_SSL(host, port, ssl_context=ssl.create_default_context(), timeout=TIMEOUT)
        self.im.login(self.env["MAIL_ADDRESS"].strip(), self.env["MAIL_PASSWORD"])
        return self.im

    def __exit__(self, *exc):
        try:
            self.im.logout()
        except Exception:  # noqa: BLE001
            pass
        return False


def _folder(name):
    name = (name or "INBOX").strip()
    return name if name.startswith('"') else '"' + name.replace('"', '\\"') + '"'


def _since(days):
    d = datetime.now() - timedelta(days=max(1, int(days)))
    return d.strftime("%d-%b-%Y")


def _search(im, *criteria):
    typ, data = im.uid("SEARCH", None, *criteria)
    if typ != "OK":
        return []
    return (data[0] or b"").split()


def _fetch_raw(im, uids):
    out = []
    for i in range(0, len(uids), 50):
        chunk = b",".join(uids[i:i + 50])
        typ, data = im.uid("FETCH", chunk, "(BODY.PEEK[])")
        if typ != "OK":
            continue
        for part in data:
            if isinstance(part, tuple) and len(part) >= 2:
                out.append(part[1])
    return out


def _clean_id(v):
    return (v or "").strip().strip("<>").strip()


def _text_of(msg):
    """The plain-text body, or the HTML body with the tags taken out."""
    plain, html = None, None
    for part in msg.walk() if msg.is_multipart() else [msg]:
        if part.get_content_maintype() == "multipart" or part.get_filename():
            continue
        ctype = part.get_content_type()
        try:
            content = part.get_content()
        except Exception:  # noqa: BLE001
            payload = part.get_payload(decode=True) or b""
            content = payload.decode(part.get_content_charset() or "utf-8", "replace")
        if not isinstance(content, str):
            continue
        if ctype == "text/plain" and plain is None:
            plain = content
        elif ctype == "text/html" and html is None:
            html = content
    if plain is not None:
        return plain.replace("\r\n", "\n").strip()
    if html is not None:
        t = re.sub(r"(?is)<(script|style).*?</\1>", " ", html)
        t = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</li>", "\n", t)
        t = re.sub(r"<[^>]+>", " ", t)
        t = re.sub(r"&nbsp;", " ", t)
        t = re.sub(r"&amp;", "&", t)
        t = re.sub(r"[ \t]+", " ", t.replace("\r\n", "\n"))
        return re.sub(r"\n\s*\n+", "\n\n", t).strip()
    return ""


def _iso(date_header):
    try:
        d = parsedate_to_datetime(date_header)
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d.isoformat()
    except Exception:  # noqa: BLE001
        return datetime.now(timezone.utc).isoformat()


def parse_message(raw):
    """One raw RFC 822 message as the dict app.py reads. The thread id is the first Message-ID in
    References (the conversation's root), else In-Reply-To, else the message's own id, so a reply and
    the email it answers share one."""
    msg = email.message_from_bytes(raw, policy=email.policy.default)
    mid = _clean_id(msg.get("Message-ID"))
    refs = re.findall(r"<([^>]+)>", str(msg.get("References") or ""))
    irt = re.findall(r"<([^>]+)>", str(msg.get("In-Reply-To") or ""))
    if not mid:
        import hashlib
        mid = "noid-" + hashlib.sha1(raw[:4000]).hexdigest()[:20]
    name, addr = parseaddr(str(msg.get("From") or ""))
    return {"id": mid, "thread_id": (refs[0] if refs else irt[0] if irt else mid),
            "date": _iso(msg.get("Date")), "from_address": (addr or "").lower(), "from_name": name or "",
            "to": str(msg.get("To") or ""), "subject": str(msg.get("Subject") or ""), "text": _text_of(msg)}


def fetch(env, days, sent=False):
    """Mail received in the last `days` days (or, with `sent`, mail you sent), oldest first. Read only."""
    folder = env.get("MAIL_SENT_FOLDER") if sent else (env.get("MAIL_INBOX_FOLDER") or "INBOX")
    if sent and not (folder or "").strip():
        raise MailError("MAIL_SENT_FOLDER is not set in .env (docs/email.md)")
    me = (env.get("MAIL_ADDRESS") or "").strip().lower()
    with _imap(env) as im:
        typ, _ = im.select(_folder(folder), readonly=True)
        if typ != "OK":
            raise MailError(f"could not open the mail folder {folder}")
        uids = _search(im, "SINCE", _since(days))[-MAX_MESSAGES:]
        out = []
        for raw in _fetch_raw(im, uids):
            try:
                m = parse_message(raw)
            except Exception:  # noqa: BLE001
                continue
            # A combined folder (Gmail's All Mail) holds your own sent mail too: received reads skip it.
            if not sent and me and m["from_address"] == me:
                continue
            out.append(m)
    return sorted(out, key=lambda m: m["date"])


# ── bounces (read only) ──────────────────────────────────────────────────────

BOUNCE_FROM = ("mailer-daemon", "postmaster")
BOUNCE_SUBJECTS = ("Undeliverable", "Delivery Status Notification", "Undelivered Mail", "Mail delivery failed",
                   "Returned mail", "Delivery Failure", "failure notice")
_STATUS = re.compile(r"\b([245]\.\d{1,3}\.\d{1,3})\b")
_CODE = re.compile(r"\b([245]\d\d)\b")
_ADDR = re.compile(r"[A-Za-z0-9._%+'-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")


def _grp(rx, s):
    m = rx.search(s or "")
    return m.group(1) if m else ""


def _dsn_groups(msg):
    """Per-recipient fields from a message/delivery-status part (RFC 3464), as dicts of lower-case keys."""
    groups = []
    for part in msg.walk():
        if part.get_content_type() != "message/delivery-status":
            continue
        payload = part.get_payload()
        blocks = payload if isinstance(payload, list) else []
        if not blocks:
            text = part.get_payload(decode=True) or b""
            blocks = [email.message_from_bytes(b, policy=email.policy.default)
                      for b in re.split(rb"\r?\n\r?\n", text) if b.strip()]
        for b in blocks:
            d = {k.lower(): str(v) for k, v in b.items()}
            if d.get("final-recipient") or d.get("original-recipient"):
                groups.append(d)
    return groups


def parse_bounce(raw, me=""):
    """The failed recipients a bounce reports: [{recipient, code, status, reason, permanent, date}]."""
    msg = email.message_from_bytes(raw, policy=email.policy.default)
    when = _iso(msg.get("Date"))
    out = []
    for g in _dsn_groups(msg):
        rcpt = (g.get("final-recipient") or g.get("original-recipient") or "").split(";")[-1].strip().strip("<>").lower()
        status = (g.get("status") or "").strip()
        diag = re.sub(r"\s+", " ", (g.get("diagnostic-code") or "").split(";", 1)[-1]).strip()
        action = (g.get("action") or "").strip().lower()
        code = _grp(_CODE, diag)
        if rcpt:
            out.append({"recipient": rcpt, "code": code, "status": status, "reason": diag[:300] or action,
                        "permanent": action == "failed" or status.startswith("5"), "date": when})
    if out:
        return out
    # No delivery-status part: read the human text the way a person would.
    text = _text_of(msg)
    status, code = _grp(_STATUS, text), _grp(_CODE, text)
    skip = {me.lower()} if me else set()
    for a in dict.fromkeys(x.lower() for x in _ADDR.findall(text)):
        if a in skip or a.split("@")[0] in BOUNCE_FROM:
            continue
        line = next((ln.strip() for ln in text.splitlines() if a in ln.lower()), "")
        out.append({"recipient": a, "code": code, "status": status, "reason": line[:300] or text[:300],
                    "permanent": status.startswith("5") or code.startswith("5"), "date": when})
        break       # the first address a plain-text bounce names is the one that failed
    return out


def find_bounces(env, days=14):
    """Delivery failures that arrived in the last `days` days. Read only."""
    me = (env.get("MAIL_ADDRESS") or "").strip().lower()
    with _imap(env) as im:
        typ, _ = im.select(_folder(env.get("MAIL_INBOX_FOLDER") or "INBOX"), readonly=True)
        if typ != "OK":
            raise MailError("could not open the inbox")
        since = _since(days)
        uids = set()
        for who in BOUNCE_FROM:
            uids.update(_search(im, "SINCE", since, "FROM", f'"{who}"'))
        for subj in BOUNCE_SUBJECTS:
            uids.update(_search(im, "SINCE", since, "SUBJECT", f'"{subj}"'))
        found = []
        for raw in _fetch_raw(im, sorted(uids, key=int)[-MAX_MESSAGES:]):
            try:
                found += parse_bounce(raw, me)
            except Exception:  # noqa: BLE001
                continue
    return found
