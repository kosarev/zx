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


def test_inactive_beeper() -> None:
    # An inactive beeper is indistinguishable from an absent one: it
    # publishes no sound.
    assert count_published_chunks(Beeper()) == 0
    assert count_published_chunks(Beeper(active=True)) == 1


def test_beeper_snapshot() -> None:
    # Activity is captured as the difference from the reset state and
    # applied by snapshot installs.
    assert Beeper().to_snapshot() is None

    beeper = Beeper(active=True)
    snapshot = beeper.to_snapshot()
    assert snapshot is not None
    assert snapshot.active

    devices = Dispatcher([beeper], devices_by_id={'beeper': beeper})
    devices.notify(InstallDeviceSnapshot(BeeperSnapshot(active=False)),
                   device='beeper')
    assert not beeper.active

    devices.notify(InstallDeviceSnapshot(BeeperSnapshot(active=True)),
                   device='beeper')
    assert beeper.active

    # A device snapshot that does not mention the activity means the
    # reset state: inactive.
    devices.notify(InstallDeviceSnapshot(BeeperSnapshot()),
                   device='beeper')
    assert not beeper.active
