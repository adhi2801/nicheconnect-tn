"""A real HTTP server on 127.0.0.1 that misbehaves on purpose (item 118, D-186).

The outside world's worst days, made on a real socket so the clients' real
transports meet them: a fake transport can return late, but it cannot hold
a socket open, so it cannot prove a limit cuts one.

- `silent`: reads the request, then never answers;
- `trickle_headers`: starts an answer and sends its headers one byte every
  `gap` seconds, for ever, each byte inside any read timeout;
- `trickle_body`: sends whole headers announcing a long body, then the body
  one byte every `gap` seconds;
- `silent_body`: sends whole headers announcing a long body, then nothing;
- `flaky`: answers the first request `fail_status`, every later one `status`
  with `body`;
- `answer`: answers every request `status` with `body`;
- `deaf`: accepts the connection and never reads from it or answers, so a
  TLS handshake gets no reply and a large request fills the socket's
  buffers and stops;
- `slow_reader`: reads `read_bytes` of what it is sent every `gap` seconds,
  and never answers.

`receive_buffer` makes the listener's receive buffer that small, so a client
sending a large request fills it quickly. `full_backlog` is a listener that
never accepts and whose queue is full, so a new connection stalls.

Every connection is closed after its answer, so each try is a new one.
"""

import socket
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
from typing import Literal

Behaviour = Literal[
    "silent",
    "trickle_headers",
    "trickle_body",
    "silent_body",
    "flaky",
    "answer",
    "deaf",
    "slow_reader",
]
# Behaviours that never read the request: they act on the socket at once.
_UNREAD = frozenset({"deaf", "slow_reader"})

REASONS = {
    200: "OK",
    400: "Bad Request",
    500: "Internal Server Error",
    503: "Unavailable",
}


class MisbehavingServer:
    def __init__(
        self,
        behaviour: Behaviour,
        *,
        status: int = 200,
        body: bytes = b'{"ok": true}',
        content_type: str = "application/json",
        fail_status: int = 503,
        gap: float = 0.2,
        extra_headers: dict[str, str] | None = None,
        receive_buffer: int | None = None,
        read_bytes: int = 1024,
    ) -> None:
        self.behaviour = behaviour
        self.status = status
        self.body = body
        self.content_type = content_type
        self.fail_status = fail_status
        self.gap = gap
        self.extra_headers = extra_headers or {}
        self.read_bytes = read_bytes
        self.requests: list[bytes] = []
        self.connections = 0
        self.received = 0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._listener = socket.socket()
        if receive_buffer is not None:
            # Before listening, so every accepted socket starts with it.
            self._listener.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, receive_buffer)
        self._listener.bind(("127.0.0.1", 0))
        self._listener.listen()
        self._listener.settimeout(0.1)
        self.port = self._listener.getsockname()[1]
        self._threads: list[threading.Thread] = []

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    # --- running -----------------------------------------------------------

    def start(self) -> None:
        accepting = threading.Thread(target=self._accept, daemon=True)
        accepting.start()
        self._threads.append(accepting)

    def stop(self) -> None:
        self._stop.set()
        self._listener.close()
        for thread in self._threads:
            thread.join(timeout=5)

    def _accept(self) -> None:
        while not self._stop.is_set():
            try:
                conn, _ = self._listener.accept()
            except TimeoutError:
                continue
            except OSError:
                return
            serving = threading.Thread(target=self._serve, args=(conn,), daemon=True)
            serving.start()
            self._threads.append(serving)

    def _serve(self, conn: socket.socket) -> None:
        with self._lock:
            self.connections += 1
        try:
            if self.behaviour in _UNREAD:
                getattr(self, f"_{self.behaviour}")(conn, self.connections)
                return
            request = self._read_request(conn)
            if request is None:
                return
            with self._lock:
                self.requests.append(request)
                number = len(self.requests)
            getattr(self, f"_{self.behaviour}")(conn, number)
        except OSError:
            pass  # the client gave up: exactly what the tests want
        finally:
            conn.close()

    def _read_request(self, conn: socket.socket) -> bytes | None:
        conn.settimeout(5)
        data = b""
        while b"\r\n\r\n" not in data:
            chunk = conn.recv(65536)
            if not chunk:
                return None
            data += chunk
        head, _, rest = data.partition(b"\r\n\r\n")
        length = 0
        for line in head.split(b"\r\n")[1:]:
            name, _, value = line.partition(b":")
            if name.strip().lower() == b"content-length":
                length = int(value.strip())
        while len(rest) < length:
            chunk = conn.recv(65536)
            if not chunk:
                break
            rest += chunk
        return head + b"\r\n\r\n" + rest

    # --- the behaviours ----------------------------------------------------

    def _head(self, status: int, length: int) -> bytes:
        lines = [
            f"HTTP/1.1 {status} {REASONS.get(status, 'Status')}",
            f"Content-Type: {self.content_type}",
            f"Content-Length: {length}",
            "Connection: close",
            *(f"{name}: {value}" for name, value in self.extra_headers.items()),
        ]
        return ("\r\n".join(lines) + "\r\n\r\n").encode()

    def _drip(self, conn: socket.socket, byte: bytes) -> None:
        while not self._stop.wait(self.gap):
            conn.sendall(byte)

    def _silent(self, conn: socket.socket, number: int) -> None:
        self._stop.wait()

    def _trickle_headers(self, conn: socket.socket, number: int) -> None:
        conn.sendall(b"HTTP/1.1 200 OK\r\nX-Slow: ")
        self._drip(conn, b"a")

    def _trickle_body(self, conn: socket.socket, number: int) -> None:
        conn.sendall(self._head(self.status, 10_000_000))
        self._drip(conn, b" ")

    def _silent_body(self, conn: socket.socket, number: int) -> None:
        conn.sendall(self._head(self.status, 10_000_000))
        self._stop.wait()

    def _deaf(self, conn: socket.socket, number: int) -> None:
        self._stop.wait()

    def _slow_reader(self, conn: socket.socket, number: int) -> None:
        conn.settimeout(5)
        while not self._stop.wait(self.gap):
            got = conn.recv(self.read_bytes)
            if not got:
                return
            with self._lock:
                self.received += len(got)

    def _flaky(self, conn: socket.socket, number: int) -> None:
        if number == 1:
            conn.sendall(self._head(self.fail_status, 0))
        else:
            self._answer(conn, number)

    def _answer(self, conn: socket.socket, number: int) -> None:
        conn.sendall(self._head(self.status, len(self.body)) + self.body)


@contextmanager
def misbehaving(behaviour: Behaviour, **options: object) -> Iterator[MisbehavingServer]:
    server = MisbehavingServer(behaviour, **options)  # type: ignore[arg-type]
    server.start()
    try:
        yield server
    finally:
        server.stop()


@contextmanager
def full_backlog() -> Iterator[str]:
    """The URL of a listener that never accepts, its queue already full.

    A new connection then stalls: Linux drops its SYN while the queue is
    full, so the client waits out its connect timeout; Windows answers the
    SYN with a reset, which its client tries again for about 2 s
    (measured 13 November 2026) before refusing.
    """
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(0)
    port = listener.getsockname()[1]
    fillers: list[socket.socket] = []
    try:
        for _ in range(16):
            filler = socket.socket()
            filler.setblocking(False)
            with suppress(BlockingIOError, ConnectionRefusedError):
                filler.connect(("127.0.0.1", port))
            fillers.append(filler)
        # Let the fillers' handshakes land in the queue before the test connects.
        time.sleep(0.3)
        yield f"http://127.0.0.1:{port}"
    finally:
        for filler in fillers:
            filler.close()
        listener.close()


def timed[T](
    call: Callable[[], T], *, give_up_after: float = 15.0
) -> tuple[object, float]:
    """Run `call` and measure it, returning what it returned or raised, and the seconds.

    In a thread of its own, so a limit that does not hold fails the test
    after `give_up_after` seconds instead of hanging the suite.
    """
    outcome: list[object] = []

    def run() -> None:
        try:
            outcome.append(call())
        except BaseException as error:
            outcome.append(error)

    started = time.monotonic()
    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    worker.join(give_up_after)
    elapsed = time.monotonic() - started
    if worker.is_alive():
        raise AssertionError(
            f"still running after {give_up_after} s: the limit did not hold"
        )
    return outcome[0], elapsed
