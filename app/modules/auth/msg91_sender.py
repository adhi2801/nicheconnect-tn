"""Login codes by WhatsApp, through MSG91 (D-058).

Sends one approved WhatsApp *authentication* template, with our own code in
its body and in its copy-code button. We generate the code (D-011); MSG91
only delivers it.

External-call rules (`backend.md` section 6): a 3 s connect and 10 s read
timeout, at most 3 attempts, exponential backoff with jitter, and retries
only where a retry can help: a network failure, 429, or a 5xx. A 4xx means
the request itself is wrong, and sending it again would only repeat that.

Nothing here logs or raises a phone number, a code, or MSG91's reply text,
which can echo either (`backend.md` section 9). Errors carry the status code
and the error type, nothing else.

**To confirm when the account exists.** MSG91's public documentation shows
the endpoint, the `authkey` header, `integrated_number`, and that the code
goes in `body_1` and the copy-code `button_1`. The full body below follows
that; MSG91's dashboard generates the exact request for each approved
template, and `build_payload` must be checked against it before the first
real send. It is the only place the shape lives.
"""

import logging
import random
import time
from collections.abc import Callable
from typing import Any

import httpx2

logger = logging.getLogger(__name__)

API_URL = "https://api.msg91.com/api/v5/whatsapp/whatsapp-outbound-message/bulk/"
TIMEOUT = httpx2.Timeout(10.0, connect=3.0)
MAX_ATTEMPTS = 3
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
BASE_DELAY_SECONDS = 0.5


class OtpDeliveryFailed(RuntimeError):
    """The code could not be delivered. The message never names the phone or code."""


def build_payload(
    *, integrated_number: str, template: str, language: str, to: str, code: str
) -> dict[str, Any]:
    """The request body for one authentication message. See the module note."""
    return {
        "integrated_number": integrated_number,
        "content_type": "template",
        "payload": {
            "messaging_product": "whatsapp",
            "type": "template",
            "template": {
                "name": template,
                "language": {"code": language, "policy": "deterministic"},
                "to_and_components": [
                    {
                        "to": [to],
                        "components": {
                            "body_1": {"type": "text", "value": code},
                            # The copy-code button carries the code as well.
                            "button_1": {"subtype": "url", "type": "text", "value": code},
                        },
                    }
                ],
            },
        },
    }


def _reply_says_failed(response: httpx2.Response) -> bool:
    """MSG91 can answer 200 and still report a failure in the body."""
    try:
        body = response.json()
    except ValueError:
        return False
    return isinstance(body, dict) and (
        body.get("hasError") is True or body.get("status") in ("fail", "error")
    )


class Msg91WhatsAppSender:
    """An `OtpSender` that delivers codes as a WhatsApp authentication message."""

    def __init__(
        self,
        *,
        auth_key: str,
        integrated_number: str,
        template: str,
        language: str,
        client: httpx2.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
        jitter: Callable[[], float] = random.random,
    ) -> None:
        self._auth_key = auth_key
        self._integrated_number = integrated_number
        self._template = template
        self._language = language
        # One client, so connections are reused between codes.
        self._client = client or httpx2.Client(timeout=TIMEOUT)
        self._sleep = sleep
        self._jitter = jitter

    def send_code(self, phone: str, code: str) -> None:
        """Deliver `code` to `phone` (E.164, +91...). Raises OtpDeliveryFailed."""
        payload = build_payload(
            integrated_number=self._integrated_number,
            template=self._template,
            language=self._language,
            # MSG91 writes numbers as digits with the country code, no plus.
            to=phone.removeprefix("+"),
            code=code,
        )
        headers = {"authkey": self._auth_key, "accept": "application/json"}

        failure = "no attempt made"
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                response = self._client.post(API_URL, json=payload, headers=headers)
            except httpx2.TransportError as exc:
                failure = type(exc).__name__
            else:
                if response.status_code in RETRY_STATUSES:
                    failure = f"status {response.status_code}"
                elif response.is_success and not _reply_says_failed(response):
                    return
                else:
                    # The request itself is wrong: a retry would repeat it.
                    raise OtpDeliveryFailed(
                        f"MSG91 refused the message (status {response.status_code})"
                    )
            logger.warning("otp.msg91_retry attempt=%d reason=%s", attempt, failure)
            if attempt < MAX_ATTEMPTS:
                # 0.5 s, then 1 s, each scaled by 0.5 to 1.5 so that many
                # clients failing together do not retry together.
                delay = BASE_DELAY_SECONDS * 2 ** (attempt - 1)
                self._sleep(delay * (0.5 + self._jitter()))
        raise OtpDeliveryFailed(
            f"MSG91 unreachable after {MAX_ATTEMPTS} attempts ({failure})"
        )
