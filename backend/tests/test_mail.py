"""Unit test for app.services.mail against an in-process SMTP server
(aiosmtpd). Runs fast, no network, no real SMTP account needed.

Covers the spam-deliverability shape of the outgoing message:
- From header carries a display name (not just a raw address).
- Reply-To and List-Unsubscribe headers are present.
- plain-text and HTML parts are both real content, not stripped HTML.
- Subject is the localized form built by build_issue_email.
"""

from __future__ import annotations

import asyncio
import importlib
from datetime import date

import pytest
from aiosmtpd.controller import Controller


class _Sink:
    """Records every envelope delivered to the in-process SMTPD."""

    def __init__(self):
        self.envelopes: list[dict] = []

    async def handle_DATA(self, server, session, envelope):
        self.envelopes.append(
            {
                "mail_from": envelope.mail_from,
                "rcpt_tos": list(envelope.rcpt_tos),
                "content": envelope.content,
            }
        )
        return "250 OK"


@pytest.fixture
def smtp_server():
    # aiosmtpd's Controller with port=0 occasionally fails its internal
    # connection self-trigger inside Docker (IPv6/IPv4 ordering). Grab a
    # free port manually and pass it explicitly so the trigger target is
    # unambiguous.
    import socket

    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    free_port = probe.getsockname()[1]
    probe.close()

    sink = _Sink()
    controller = Controller(sink, hostname="127.0.0.1", port=free_port, server_hostname="localhost")
    controller.start()
    try:
        yield sink, controller.hostname, controller.port
    finally:
        controller.stop()


def _configure_smtp(monkeypatch, host, port):
    from app import config as config_module

    monkeypatch.setattr(config_module.settings, "smtp_host", host)
    monkeypatch.setattr(config_module.settings, "smtp_port", port)
    monkeypatch.setattr(config_module.settings, "smtp_user", "")
    monkeypatch.setattr(config_module.settings, "smtp_password", "")
    monkeypatch.setattr(config_module.settings, "smtp_from", "sender@example.invalid")
    # aiosmtpd doesn't negotiate STARTTLS by default; disable so aiosmtplib
    # doesn't hang trying to upgrade the plain channel.
    monkeypatch.setattr(config_module.settings, "smtp_use_tls", False)

    from app.services import mail as mail_module

    importlib.reload(mail_module)
    return mail_module


def test_send_issue_delivers_per_recipient_and_includes_headers(smtp_server, monkeypatch):
    sink, host, port = smtp_server
    mail_module = _configure_smtp(monkeypatch, host, port)

    payload = mail_module.build_issue_email(
        paper_name="The Daily Crosswire",
        issue_date=date(2026, 4, 22),
        language="en",
        slug="2026-04-22-daily-crosswire",
        pdf_bytes=b"%PDF-1.4 tiny fake pdf",
        kind="auto",
    )
    recipients = ["alice@example.invalid", "bob@example.invalid"]
    outcomes = asyncio.run(mail_module.send_issue(recipients, payload))

    assert len(outcomes) == 2
    assert [o["email"] for o in outcomes] == recipients
    assert all(o["status"] == "ok" for o in outcomes)

    # One envelope per recipient (no leak).
    assert len(sink.envelopes) == 2
    for env in sink.envelopes:
        assert len(env["rcpt_tos"]) == 1
    rcpts = sorted(e["rcpt_tos"][0] for e in sink.envelopes)
    assert rcpts == sorted(recipients)

    # Shape of every envelope: From with display name, Reply-To, List-Unsubscribe.
    for env in sink.envelopes:
        content = env["content"].decode("utf-8", errors="replace")
        assert "From: The Daily Crosswire <sender@example.invalid>" in content
        assert "Reply-To: sender@example.invalid" in content
        assert "List-Unsubscribe: <mailto:sender@example.invalid?subject=Unsubscribe>" in content
        # Subject uses middot separator and localized long date.
        assert "Subject: The Daily Crosswire" in content
        # multipart wrapping: plain + html alternative + pdf attachment.
        assert "multipart/alternative" in content
        assert 'filename="2026-04-22-daily-crosswire.pdf"' in content


def test_build_issue_email_localizes_body_and_subject():
    from app.services import mail as mail_module

    # Spanish ad-hoc send of a past issue. greeting_adhoc should include
    # the formatted date; subject uses the same date in the Spanish form.
    payload = mail_module.build_issue_email(
        paper_name="El Crosswire",
        issue_date=date(2026, 4, 22),
        language="es",
        slug="2026-04-22",
        pdf_bytes=b"",
        kind="adhoc",
    )
    assert "Comparto la edición de El Crosswire" in payload.text_body
    assert "Comparto la edición de El Crosswire" in payload.html_body
    assert "abril" in payload.text_body.lower()
    assert " · " in payload.subject
    assert "El Crosswire" in payload.subject
    # Plain body is real text, not stripped HTML: contains newlines + sig.
    assert payload.text_body.endswith("El Crosswire\n")
    assert "-- \n" in payload.text_body


def test_send_issue_raises_when_smtp_misconfigured(monkeypatch):
    from app import config as config_module
    from app.services import mail as mail_module

    monkeypatch.setattr(config_module.settings, "smtp_host", "")
    monkeypatch.setattr(config_module.settings, "smtp_from", "")
    importlib.reload(mail_module)

    payload = mail_module.build_issue_email(
        paper_name="Test",
        issue_date=date(2026, 1, 1),
        language="en",
        slug="x",
        pdf_bytes=b"x",
        kind="auto",
    )
    with pytest.raises(RuntimeError, match="SMTP not configured"):
        asyncio.run(mail_module.send_issue(["alice@example.invalid"], payload))
