"""/.well-known/security.txt (RFC 9116, D-082): reachable, valid, and current."""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.core import security_txt
from app.core.rate_limit import limiter
from app.main import app

URL = "/.well-known/security.txt"


def fields(text: str) -> dict[str, str]:
    return dict(line.split(": ", 1) for line in text.splitlines() if line)


def test_it_is_plain_text_with_the_fields_the_rfc_requires():
    response = TestClient(app).get(URL)

    assert response.status_code == 200
    assert response.headers["content-type"] == "text/plain; charset=utf-8"
    assert response.headers["cache-control"] == "public, max-age=86400"
    found = fields(response.text)
    assert found["Contact"].startswith("https://")
    assert found["Preferred-Languages"] == "en"
    assert found["Policy"].endswith("/SECURITY.md")
    # RFC 9116 section 2.5.5: an internet date-time, in UTC here.
    expires = datetime.fromisoformat(found["Expires"])
    assert expires == security_txt.EXPIRES


def test_it_needs_no_login_and_names_nothing_about_the_caller():
    plain = TestClient(app).get(URL)
    signed_in = TestClient(app).get(URL, headers={"Authorization": "Bearer x"})

    assert plain.text == signed_in.text


def test_expires_is_at_most_a_year_ahead_of_today():
    # The RFC's own limit, so an expiry can never be set and forgotten.
    assert security_txt.EXPIRES - datetime.now(UTC) <= timedelta(days=366)


def test_renew_it_before_it_lapses():
    """Fails 30 days before Expires, on the real date, on purpose: this is the
    reminder. Renew by moving EXPIRES in app/core/security_txt.py (at most a
    year ahead) after checking the contact still reaches a founder."""
    left = security_txt.EXPIRES - datetime.now(UTC)

    assert left > timedelta(days=30), f"security.txt expires in {left.days} days"


def test_it_is_rate_limited():
    limiter.reset()
    client = TestClient(app)
    try:
        answers = [client.get(URL).status_code for _ in range(61)]
    finally:
        limiter.reset()

    assert answers[:60] == [200] * 60
    assert answers[60] == 429
