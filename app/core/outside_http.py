"""One HTTP exchange with the outside world that never outlives its call's limit (item 118, D-186).

Every client that calls out over HTTP (WhatsApp through MSG91, the DNS and
RDAP lookups, Instagram and YouTube, the timestamp authorities) sends each
try through `exchange`, inside one `Deadline` for the whole call:

- the client's own limits (connect 3 s, read 10 s; backend.md section 6) are
  each cut to the time left, so a late try cannot wait its full 10 s;
- the answer is read piece by piece, and the call stops as soon as its limit
  passes, so a server that trickles a byte at a time, each inside the read
  timeout, is cut off rather than holding a worker for ever.

**What it cannot do:** shorten a wait already begun. httpx2 fixes a read's
timeout when the read starts, so a call can end at most one read wait (10 s)
after its limit, and the headers' own reads are bounded only per wait. The
limit is checked before every try and after every piece.
"""

from typing import Any

import httpx2

from app.core.deadline import Deadline


class CallLimitReached(httpx2.TimeoutException):
    """The call's whole limit passed, across its tries, before its answer was read.

    A `TimeoutException`, so every client's existing handling of a
    transport failure applies to it unchanged.
    """


def exchange(
    client: httpx2.Client,
    method: str,
    url: str,
    deadline: Deadline,
    **request: Any,
) -> httpx2.Response:
    """Send one request and read its whole answer, stopping at `deadline`.

    Raises CallLimitReached, or the transport's own errors.
    """
    if deadline.expired():
        raise CallLimitReached("the call's limit passed before this try")
    own = client.timeout
    timeout = httpx2.Timeout(
        connect=deadline.capped(own.connect),
        read=deadline.capped(own.read),
        write=deadline.capped(own.write),
        pool=deadline.capped(own.pool),
    )
    with client.stream(method, url, timeout=timeout, **request) as response:
        pieces: list[bytes] = []
        for piece in response.iter_raw():
            pieces.append(piece)
            if deadline.expired():
                raise CallLimitReached(
                    "the call's limit passed while its answer was read"
                )
        # The bytes exactly as sent, with the headers that say how to read
        # them, so a compressed answer is decoded as httpx2 would.
        return httpx2.Response(
            response.status_code,
            headers=response.headers,
            content=b"".join(pieces),
            request=response.request,
        )
