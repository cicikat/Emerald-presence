"""OLED output adapter scaffold.

Display content is supplied by the caller. This adapter only serializes a
low-level command into a dummy byte frame for an injected transport.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from core.hardware.base import OutputDevice
from core.hardware.transports.base import Transport


@dataclass(frozen=True)
class OledCommand:
    text: str
    clear: bool
    x: int
    y: int
    size: int

    def __post_init__(self) -> None:
        if not isinstance(self.text, str):
            raise ValueError("text must be a string")
        if not isinstance(self.clear, bool):
            raise ValueError("clear must be a bool")
        for field_name in ("x", "y", "size"):
            value = getattr(self, field_name)
            if not isinstance(value, int) or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")


class OledDevice(OutputDevice):
    def __init__(
        self,
        transport: Transport,
        device_id: str = "oled.default",
        *,
        dry_run: bool = True,
    ) -> None:
        self.transport = transport
        self._device_id = device_id
        self.dry_run = dry_run

    @property
    def device_id(self) -> str:
        return self._device_id

    @property
    def modality(self) -> str:
        return "oled"

    @property
    def dangerous(self) -> bool:
        return False

    async def send_command(self, command: object) -> None:
        if not isinstance(command, OledCommand):
            raise TypeError("command must be an OledCommand")
        self.accept(command)

    def accept(self, command: OledCommand) -> None:
        if not isinstance(command, OledCommand):
            raise TypeError("command must be an OledCommand")
        self.transport.send_frame(_serialize_command(self.device_id, self.dry_run, command))


def _serialize_command(device_id: str, dry_run: bool, command: OledCommand) -> bytes:
    frame = {
        "device": "oled",
        "device_id": device_id,
        "dry_run": dry_run,
        "command": {
            "text": command.text,
            "clear": command.clear,
            "x": command.x,
            "y": command.y,
            "size": command.size,
        },
    }
    return json.dumps(frame, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
