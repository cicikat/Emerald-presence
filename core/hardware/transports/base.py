"""Hardware byte transport contracts.

Transports are raw byte links. They do not know device semantics, application
state, prompts, schedulers, LLMs, or project data files.
"""

from abc import ABC, abstractmethod


class Transport(ABC):
    @property
    @abstractmethod
    def transport_id(self) -> str:
        """Stable in-process identifier for this byte link."""

    @property
    @abstractmethod
    def connected(self) -> bool:
        """Whether the byte link is currently considered connected."""

    @abstractmethod
    def send_frame(self, frame: bytes) -> None:
        """Send one raw byte frame."""

    @abstractmethod
    def recv_frame(self) -> bytes:
        """Receive one raw byte frame, or b'' when none is available."""
