#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.


import pytest

from zx._device import Device
from zx._device import DeviceEvent
from zx._device import Dispatcher


class _Recorder(Device):
    def __init__(self) -> None:
        super().__init__()
        self.events: list[DeviceEvent] = []

    def on_event(self, event: DeviceEvent, devices: Dispatcher) -> None:
        self.events.append(event)


def test_targeted_dispatch() -> None:
    # A targeted event is delivered to the addressed device only; an
    # unknown device id is an error.
    a = _Recorder()
    b = _Recorder()
    devices = Dispatcher([a, b], devices_by_id={'a': a, 'b': b})

    broadcast = DeviceEvent()
    devices.notify(broadcast)
    assert a.events == [broadcast]
    assert b.events == [broadcast]

    targeted = DeviceEvent()
    devices.notify(targeted, device='b')
    assert a.events == [broadcast]
    assert b.events == [broadcast, targeted]

    with pytest.raises(KeyError):
        devices.notify(DeviceEvent(), device='c')
