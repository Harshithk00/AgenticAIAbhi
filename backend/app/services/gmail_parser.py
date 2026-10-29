"""Pure functions that turn Gmail API message resources into safe plain text.

Gmail returns MIME parts with base64url-encoded bodies. We prefer text/plain; for HTML-only
messages we convert HTML to text ourselves, dropping scripts, styles and remote content.
The frontend only ever receives plain text.
"""

from __future__ import annotations

import base64
import binascii
import html
import re
from datetime import datetime, timezone
from email.utils import parseaddr
from html.parser import HTMLParser

_BLOCK_TAGS = {"p", "div", "br", "tr", "li", "h1", "h2", "h3", "h4", "h5", "h6", "table", "blockquote", "hr"}
_SKIP_TAGS = {"script", "style", "head", "title", "noscript", "template", "svg", "iframe", "object"}


def decode_base64url(data: str | None) -> str:
    if not data:
        return ""
    padded = data + "=" * (-len(data) % 4)
    try:
        raw = base64.urlsafe_b64decode(padded)
    except (binascii.Error, ValueError):
        return ""
    return raw.decode("utf-8", errors="replace")


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
        elif tag in _BLOCK_TAGS and not self._skip_depth:
            self.parts.append("\n")

    def handle_startendtag(self, tag, attrs):
        if tag in _BLOCK_TAGS and not self._skip_depth:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in _SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
        elif tag in _BLOCK_TAGS and not self._skip_depth:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip_depth:
            self.parts.append(data)


def html_to_text(markup: str) -> str:
    parser = _TextExtractor()
    parser.feed(markup)
    parser.close()
    return normalize_whitespace("".join(parser.parts))


def normalize_whitespace(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\xa0", " ")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]
    text = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _walk_parts(part: dict):
    yield part
    for child in part.get("parts", []) or []:
        yield from _walk_parts(child)


def extract_body(payload: dict) -> tuple[str, bool]:
    """Return (plain_text_body, was_html). Attachments are ignored."""
    plain, rich = [], []
    for part in _walk_parts(payload or {}):
        if part.get("filename"):
            continue  # attachment
        mime = (part.get("mimeType") or "").lower()
        data = (part.get("body") or {}).get("data")
        if not data:
            continue
        if mime == "text/plain":
            plain.append(decode_base64url(data))
        elif mime == "text/html":
            rich.append(decode_base64url(data))
    if plain:
        return normalize_whitespace("\n\n".join(plain)), False
    if rich:
        return html_to_text("\n".join(rich)), True
    return "", False


def header_map(payload: dict) -> dict[str, str]:
    return {h.get("name", "").lower(): h.get("value", "") for h in (payload or {}).get("headers", []) or []}


def parse_internal_date(value: str | None) -> datetime | None:
    try:
        return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc)
    except (TypeError, ValueError):
        return None


def sender_email(sender: str) -> str:
    return parseaddr(sender)[1].lower()


def parse_message(message: dict) -> dict:
    """Normalise a Gmail `users.messages.get` resource (format=full or metadata)."""
    payload = message.get("payload") or {}
    headers = header_map(payload)
    labels = message.get("labelIds") or []
    body_text, was_html = extract_body(payload)
    return {
        "id": message["id"],
        "thread_id": message.get("threadId"),
        "sender": headers.get("from", ""),
        "to": headers.get("to", ""),
        "subject": headers.get("subject", "") or "(no subject)",
        "snippet": html.unescape(message.get("snippet", "")),
        "received_at": parse_internal_date(message.get("internalDate")),
        "unread": "UNREAD" in labels,
        "labels": labels,
        "body_text": body_text,
        "body_was_html": was_html,
    }
