from pathlib import Path
from unittest.mock import Mock

from core.hardware.adapters.oled import OledCommand, OledDevice
from core.hardware.transports.mock_transport import MockTransport


def test_oled_accept_sends_serialized_frame_to_transport():
    transport = MockTransport()
    transport.send_frame = Mock()
    device = OledDevice(transport)

    device.accept(OledCommand(text="hello", clear=True, x=1, y=2, size=3))

    transport.send_frame.assert_called_once()
    frame = transport.send_frame.call_args.args[0]
    assert isinstance(frame, bytes)
    assert b"oled" in frame
    assert b"hello" in frame


def test_oled_adapter_has_no_upper_layer_imports():
    source = Path("core/hardware/adapters/oled.py").read_text(encoding="utf-8")

    assert "core.memory" not in source
    assert "core.embodiment" not in source
    assert "diary" not in source
    assert "identity" not in source
