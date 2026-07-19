#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.


from zx._beeper import Beeper
from zx._beeper import BeeperSnapshot
from zx._device import Device
from zx._device import DeviceEvent
from zx._device import Dispatcher
from zx._device import InstallDeviceSnapshot
from zx._device import NewSoundPulses
from zx._device import TimeAdvanced
from zx._time import Time


class _SoundReceiver(Device):
    def __init__(self) -> None:
        super().__init__()
        self.num_chunks = 0

    def on_event(self, event: DeviceEvent, devices: Dispatcher) -> None:
        if isinstance(event, NewSoundPulses):
            self.num_chunks += 1


# The number of sound chunks the beeper publishes over two time
# advances: the first one only synchronises, the second publishes the
# elapsed span.
def count_published_chunks(beeper: Beeper) -> int:
    receiver = _SoundReceiver()
    devices = Dispatcher([beeper, receiver])

    devices.notify(TimeAdvanced(Time(0, ticks_per_second=100)))
    devices.notify(TimeAdvanced(Time(10, ticks_per_second=100)))

    return receiver.num_chunks


def test_disabled_beeper() -> None:
    # A disabled beeper is indistinguishable from an absent one: it
    # publishes no sound.
    assert count_published_chunks(Beeper(disabled=True)) == 0
    assert count_published_chunks(Beeper()) == 1


def test_beeper_snapshot() -> None:
    # A disabled beeper is indistinguishable from an absent one, so
    # it captures as nothing.
    assert Beeper(disabled=True).to_snapshot() is None

    beeper = Beeper()
    snapshot = beeper.to_snapshot()
    assert snapshot is not None
    assert snapshot.disabled is None

    devices = Dispatcher([beeper], devices_by_id={'beeper': beeper})
    devices.notify(InstallDeviceSnapshot(BeeperSnapshot(disabled=True)),
                   device='beeper')
    assert beeper.disabled

    # A device snapshot that does not state the flag means the reset
    # state: not disabled.
    devices.notify(InstallDeviceSnapshot(BeeperSnapshot()),
                   device='beeper')
    assert not beeper.disabled
