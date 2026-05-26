"""Motor output adapter scaffold.

This device is dangerous. When real permission handling exists, motor output
must require its own explicit confirmation and must not share a single enabled
switch with lights.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from core.hardware.base import OutputDevice
from core.hardware.transports.base import Transport


@dataclass(frozen=True)
class MotorCommand:
    angle: float
    speed: float
    duration_ms: int

    def __post_init__(self) -> None:
        if not isinstance(self.angle, (int, float)):
            raise ValueError("angle must be numeric")
        if not isinstance(self.speed, (int, float)) or float(self.speed) < 0.0:
            raise ValueError("speed must be a non-negative number")
        if not isinstance(self.duration_ms, int) or self.duration_ms < 0:
            raise ValueError("duration_ms must be a non-negative integer")


class MotorDevice(OutputDevice):
    def __init__(
        self,
        transport: Transport,
        device_id: str = "motor.default",
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
        return "motor"

    @property
    def dangerous(self) -> bool:
        return True

    async def send_command(self, command: object) -> None:
        if not isinstance(command, MotorCommand):
            raise TypeError("command must be a MotorCommand")
        self.accept(command)

    def accept(self, command: MotorCommand) -> None:
        if not isinstance(command, MotorCommand):
            raise TypeError("command must be a MotorCommand")
        self.transport.send_frame(_serialize_command(self.device_id, self.dry_run, command))


def _serialize_command(device_id: str, dry_run: bool, command: MotorCommand) -> bytes:
    frame = {
        "device": "motor",
        "device_id": device_id,
        "dry_run": dry_run,
        "command": {
            "angle": float(command.angle),
            "speed": float(command.speed),
            "duration_ms": command.duration_ms,
        },
    }
    return json.dumps(frame, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
