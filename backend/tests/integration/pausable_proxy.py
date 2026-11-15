"""A TCP proxy in front of the test database that can stop answering (issues #4 and #95).

Used by the paused-database tests in `test_health.py` and `test_db_time_limit.py`.
"""

import socket
import threading
from dataclasses import dataclass, field

# A paused proxy resumes by itself after this long, so a test of code without a time limit
# fails instead of hanging.
PAUSE_LIMIT_SECONDS = 15


@dataclass
class _Link:
    """One proxied connection: the app's socket, the database's socket, and whether bytes flow."""

    client: socket.socket
    upstream: socket.socket
    forwarding: threading.Event = field(default_factory=threading.Event)


class PausableProxy:
    """A TCP proxy in front of the test database that can stop answering.

    `pause()` holds the bytes of every connection, open or new, like `docker compose pause db`:
    each TCP connection stays up, new ones are accepted, and nothing replies.

    `pause_open_connections()` holds the bytes of the connections already open only, and new
    connections work: as when a pooled connection is dropped silently somewhere on the
    network while the database is fine.
    """

    def __init__(self, host: str, port: int) -> None:
        self._target = (host, port)
        self._lock = threading.Lock()
        self._links: list[_Link] = []
        self._hold_new_connections = False
        self._resume_timer: threading.Timer | None = None
        self._listener = socket.create_server(("127.0.0.1", 0))
        self._listener.settimeout(0.2)
        self._closed = False
        self.port: int = self._listener.getsockname()[1]
        threading.Thread(target=self._accept, daemon=True).start()

    def pause(self, resume_after: float = PAUSE_LIMIT_SECONDS) -> None:
        with self._lock:
            self._hold_new_connections = True
            for link in self._links:
                link.forwarding.clear()
        self._resume_later(resume_after)

    def pause_open_connections(self, resume_after: float = PAUSE_LIMIT_SECONDS) -> None:
        with self._lock:
            for link in self._links:
                link.forwarding.clear()
        self._resume_later(resume_after)

    def resume(self) -> None:
        if self._resume_timer is not None:
            self._resume_timer.cancel()
        with self._lock:
            self._hold_new_connections = False
            for link in self._links:
                link.forwarding.set()

    def drop_connections(self) -> None:
        """Close every open connection, as a database restart does."""
        with self._lock:
            links, self._links = self._links, []
        for link in links:
            _close(link.client)
            _close(link.upstream)
            link.forwarding.set()  # held bytes now go nowhere: both sockets are closed

    def close(self) -> None:
        self._closed = True
        self.drop_connections()
        self.resume()

    def _resume_later(self, seconds: float) -> None:
        if self._resume_timer is not None:
            self._resume_timer.cancel()
        self._resume_timer = threading.Timer(seconds, self.resume)
        self._resume_timer.daemon = True
        self._resume_timer.start()

    def _accept(self) -> None:
        while not self._closed:
            try:
                client, _ = self._listener.accept()
            except TimeoutError:
                continue
            link = _Link(client, socket.create_connection(self._target))
            with self._lock:
                if not self._hold_new_connections:
                    link.forwarding.set()
                self._links.append(link)
            for source, destination in ((link.client, link.upstream), (link.upstream, link.client)):
                threading.Thread(
                    target=self._pump, args=(source, destination, link.forwarding), daemon=True
                ).start()
        self._listener.close()

    def _pump(
        self, source: socket.socket, destination: socket.socket, forwarding: threading.Event
    ) -> None:
        try:
            while data := source.recv(65536):
                forwarding.wait()  # hold the bytes while paused
                destination.sendall(data)
        except OSError:
            pass  # the connection was dropped
        finally:
            _close(source)
            _close(destination)


def _close(sock: socket.socket) -> None:
    try:
        sock.shutdown(socket.SHUT_RDWR)  # wakes up a thread blocked in recv()
    except OSError:
        pass
    sock.close()
