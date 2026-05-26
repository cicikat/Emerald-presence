from unittest.mock import Mock

from core.hardware.adapters.motor import MotorCommand, MotorDevice
from core.hardware.transports.mock_transport import MockTransport


def test_motor_device_is_dangerous_and_dry_run_by_default():
    device = MotorDevice(MockTransport())

    assert device.dangerous is True
    assert device.dry_run is True


def test_motor_accept_sends_serialized_frame_to_transport():
    transport = MockTransport()
    transport.send_frame = Mock()
    device = MotorDevice(transport)

    device.accept(MotorCommand(angle=30.5, speed=0.25, duration_ms=100))

    transport.send_frame.assert_called_once()
    frame = transport.send_frame.call_args.args[0]
    assert isinstance(frame, bytes)
    assert b"motor" in frame
    assert b"30.5" in frame
