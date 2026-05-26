from core.hardware.transports.mock_transport import MockTransport


def test_mock_transport_send_frame_is_log_only_and_recv_defaults_empty():
    transport = MockTransport()

    transport.send_frame(b"abc")

    assert transport.connected is True
    assert transport.recv_frame() == b""


def test_mock_transport_recv_frame_uses_injected_queue():
    transport = MockTransport(incoming=[b"one"])
    transport.inject_frame(b"two")

    assert transport.recv_frame() == b"one"
    assert transport.recv_frame() == b"two"
    assert transport.recv_frame() == b""
