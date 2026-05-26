"""In-memory mock transport for hardware adapter tests and dry runs."""

from __future__ import annotations

import logging
from collections import deque
from collections.abc import Iterable

from .base import Transport


logger = logging.getLogger(__name__)


class MockTransport(Transport):
    def __init__(self, transport_id: str = "mock.transport", incoming: Iterable[bytes] | None = None) -> None:
        self._transport_id = transport_id
        self._incoming = deque(incoming or ())

    @property
    def transport_id(self) -> str:
        return self._transport_id

    @property
    def connected(self) -> bool:
        return True

    def send_frame(self, frame: bytes) -> None:
        if not isinstance(frame, bytes):
            raise TypeError("frame must be bytes")
        logger.info("would send %d bytes: %r", len(frame), frame)

    def recv_frame(self) -> bytes:
        if not self._incoming:
            return b""
        return self._incoming.popleft()

    def inject_frame(self, frame: bytes) -> None:
        if not isinstance(frame, bytes):
            raise TypeError("frame must be bytes")
        self._incoming.append(frame)
