"""SMTP delivery for newsletter + ad-hoc issue send.

One MIME multipart per recipient so addresses don't leak across sends and
each outcome is recorded independently. aiosmtplib runs async so the
notify node doesn't block the event loop.

Deliverability headers:
- From: uses a display name (`"<paper_name>" <from_address>`) when the
  caller provides one. Raw "From: foo@bar" without a display name scores
  worse on many filters.
- Reply-To: mirrors the From address by default so replies don't fall
  into the void of a configured send-only account.
- List-Unsubscribe: mailto variant. Doing this even at tiny volumes keeps
  Gmail / Yahoo reputation signals in good shape.

Caller is responsible for `settings.smtp_configured` checks; this module
raises clear exceptions if the connection settings are missing.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from email.message import EmailMessage
from email.utils import formataddr
from html import escape
from typing import Any, Optional

import aiosmtplib

from app.agent.languages import email_strings, format_long_date
from app.config import settings

logger = logging.getLogger(__name__)


def build_issue_email(
    *,
    paper_name: str,
    issue_date: Optional[date],
    language: Optional[str],
    slug: str,
    pdf_bytes: bytes,
    kind: str = "auto",
) -> "IssueEmail":
    """Build a localized IssueEmail for the given config + issue.

    `kind="auto"` is the notify node's automatic delivery right after
    render; the greeting phrases it as "today's issue". `kind="adhoc"`
    is the preview-page Send button; the greeting includes the issue
    date because the user may be sharing an older edition. Both use the
    same structural body so filters don't treat one as more templated
    than the other.

    All localized strings come from static tables in
    app.agent.languages. No LLM call happens here.
    """
    lang = language or "en"
    strings = email_strings(lang)
    date_str = format_long_date(issue_date, lang) if issue_date else ""

    if kind == "adhoc":
        greeting = strings["greeting_adhoc"].format(paper=paper_name, date=date_str)
    else:
        greeting = strings["greeting_auto"].format(paper=paper_name, date=date_str)
    note = strings["body_note"]

    # Subject uses middot separator: safer than em-dash (brand voice) and
    # renders consistently across MUAs. Paper name stays in the user's
    # configured name (not translated).
    subject_parts = [paper_name]
    if date_str:
        subject_parts.append(date_str)
    subject = " · ".join(subject_parts)

    # Plain text body. Real content, not stripped HTML. `-- ` (dash dash
    # space) is the RFC 3676 signature delimiter convention; safe ASCII,
    # no em-dash.
    text_body = f"{greeting}\n\n{note}\n\n-- \n{paper_name}\n"

    # HTML body. Keep it plain: inline styles are fine but keep them
    # minimal and avoid tracking-looking artifacts.
    safe_paper = escape(paper_name)
    safe_greeting = escape(greeting)
    safe_note = escape(note)
    html_body = (
        '<!doctype html><html><body style="font-family: -apple-system, '
        "BlinkMacSystemFont, 'Segoe UI', sans-serif; color: #222; "
        'line-height: 1.5; max-width: 40em;">'
        f"<p>{safe_greeting}</p>"
        f"<p>{safe_note}</p>"
        '<p style="color:#888; font-size:0.9em; margin-top:2em;">'
        f"{safe_paper}</p>"
        "</body></html>"
    )

    return IssueEmail(
        subject=subject,
        text_body=text_body,
        html_body=html_body,
        pdf_bytes=pdf_bytes,
        pdf_filename=f"{slug}.pdf",
        from_name=paper_name,
    )


@dataclass
class IssueEmail:
    """Structured payload for a single-issue send. Pre-rendered plain and
    HTML bodies live here instead of being derived from each other so the
    plain part isn't just HTML-with-tags-stripped (filters notice)."""

    subject: str
    text_body: str
    html_body: str
    pdf_bytes: bytes
    pdf_filename: str
    # Display name for the From header, e.g. config.name. None falls back
    # to the raw SMTP_FROM address.
    from_name: Optional[str] = None
    # Extra RFC-2822 headers to attach. Caller adds List-Unsubscribe,
    # List-Id, or X-* headers here.
    extra_headers: dict[str, str] = field(default_factory=dict)


async def send_issue(
    recipients: list[str],
    payload: IssueEmail,
) -> list[dict[str, Any]]:
    """Send one MIME multipart/alternative per recipient with the PDF
    attached. Returns per-recipient outcomes: [{email, status, error?}].

    A single bad recipient doesn't abort the loop; its entry records the
    failure and the remaining recipients still receive their copy."""
    if not settings.smtp_configured:
        raise RuntimeError("SMTP not configured. Set SMTP_HOST and SMTP_FROM in .env.")

    from_header = (
        formataddr((payload.from_name, settings.smtp_from))
        if payload.from_name
        else settings.smtp_from
    )

    outcomes: list[dict[str, Any]] = []

    for to in recipients:
        msg = EmailMessage()
        msg["From"] = from_header
        msg["To"] = to
        msg["Subject"] = payload.subject
        # Reply-To ensures replies go somewhere real. Falls back to the
        # From address when no dedicated reply inbox is provided.
        msg["Reply-To"] = settings.smtp_from
        # List-Unsubscribe (RFC 2369) signals bulk senders in a good way.
        # mailto variant only; one-click POST (RFC 8058) would require a
        # backend handler we're not adding.
        msg["List-Unsubscribe"] = f"<mailto:{settings.smtp_from}?subject=Unsubscribe>"
        for header, value in payload.extra_headers.items():
            msg[header] = value

        # Set plain text as the primary body, then attach HTML as an
        # alternative. Python's EmailMessage handles the multipart
        # scaffolding and the attachment's own multipart/mixed wrapping.
        msg.set_content(payload.text_body)
        msg.add_alternative(payload.html_body, subtype="html")
        msg.add_attachment(
            payload.pdf_bytes,
            maintype="application",
            subtype="pdf",
            filename=payload.pdf_filename,
        )

        try:
            await aiosmtplib.send(
                msg,
                hostname=settings.smtp_host,
                port=settings.smtp_port,
                username=settings.smtp_user or None,
                password=settings.smtp_password or None,
                start_tls=settings.smtp_use_tls,
            )
            outcomes.append({"email": to, "status": "ok"})
            logger.info("mail: sent to %s (subject=%r)", to, payload.subject)
        except Exception as exc:
            outcomes.append(
                {
                    "email": to,
                    "status": "failed",
                    "error": f"{type(exc).__name__}: {str(exc)[:200]}",
                }
            )
            logger.warning("mail: failed to %s (%s): %s", to, type(exc).__name__, exc)

    return outcomes
