#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.


from __future__ import annotations

import typing

import numpy

from ._data import DeviceSnapshot
from ._device import Device
from ._device import DeviceEvent
from ._device import Dispatcher
from ._device import InstallDeviceSnapshot
from ._device import NewPortWrites
from ._device import NewSoundPulses
from ._device import ResetEmulator
from ._device import TimeAdvanced
from ._sound import PulseStream

if typing.TYPE_CHECKING:
    from ._time import Time


class BeeperSnapshot(DeviceSnapshot, format_name=None):
    active: bool | None

    def __init__(self, *, active: bool | None = None) -> None:
        super().__init__(active=active)


class Beeper(Device, snapshot_type=BeeperSnapshot):

    def __init__(self, *, active: bool = False) -> None:
        super().__init__(active=active)

        self.__stream = PulseStream()

        # The time up to which the beeper's sound has been
        # published.
        self.__published_up_to: None | Time = None

        # EAR transitions collected since then, with their
        # free-running tick stamps.
        self.__levels: list[numpy.typing.NDArray[numpy.float64]] = []
        self.__ticks: list[numpy.typing.NDArray[numpy.uint32]] = []

    @classmethod
    def from_snapshot(cls, snapshot: DeviceSnapshot) -> Beeper:
        assert isinstance(snapshot, BeeperSnapshot)
        return cls(active=snapshot.active is True)

    def to_snapshot(self) -> BeeperSnapshot | None:
        # Only the difference from the reset state is captured.
        if not self.active:
            return None

        return BeeperSnapshot(active=True)

    def __collect(self, writes: numpy.typing.NDArray[numpy.uint64]) -> None:
        # Filter writes to the 0xfe port.
        writes = writes[writes & numpy.uint64(0xff) == numpy.uint64(0xfe)]
        if len(writes) == 0:
            return

        # Get EAR levels and their tick stamps.
        EAR_BIT_POS = 16 + 4
        self.__levels.append(
            ((writes >> numpy.uint64(EAR_BIT_POS)) &
             numpy.uint64(1)).astype(numpy.float64))
        self.__ticks.append(
            (writes >> numpy.uint64(32)).astype(numpy.uint32))

    def __publish(self, stamp: Time, dispatcher: Dispatcher) -> None:
        published_up_to = self.__published_up_to
        self.__published_up_to = stamp

        # Resynchronise after construction or reset.
        if published_up_to is None:
            self.__levels.clear()
            self.__ticks.clear()
            return

        # Positions subtract only within one timeline; the
        # transitions are stamped in its ticks too. A rate change
        # comes only with a reset, which resynchronises.
        assert stamp.ticks_per_second == published_up_to.ticks_per_second
        span = stamp.count - published_up_to.count
        if span == 0:
            return

        if self.__levels:
            levels = numpy.concatenate(self.__levels)
            ticks = numpy.concatenate(self.__ticks)
            self.__levels.clear()
            self.__ticks.clear()

            # Offsets within the published span; uint32 arithmetic
            # wraps.
            ticks = ticks - numpy.uint32(published_up_to.count & 0xffffffff)
        else:
            levels = numpy.zeros(0, dtype=numpy.float64)
            ticks = numpy.zeros(0, dtype=numpy.uint32)

        pulses = self.__stream.stream_chunk(levels, ticks, span,
                                            rate=stamp.ticks_per_second)
        dispatcher.notify(NewSoundPulses(pulses))

    def __reset(self) -> None:
        self.__stream.reset()
        self.__published_up_to = None
        self.__levels.clear()
        self.__ticks.clear()

    def __install_snapshot(self, s: DeviceSnapshot) -> None:
        assert isinstance(s, BeeperSnapshot)

        # Whatever the snapshot does not mention is at reset.
        self.__reset()

        # Unmentioned activity means the reset state: inactive.
        self.active = s.active is True

    def on_event(self, event: DeviceEvent, dispatcher: Dispatcher) -> None:
        if isinstance(event, InstallDeviceSnapshot):
            self.__install_snapshot(event.snapshot)
            return

        # An inactive beeper is indistinguishable from an absent
        # one: it publishes no sound.
        if not self.active:
            return

        if isinstance(event, ResetEmulator):
            self.__reset()
        elif isinstance(event, NewPortWrites):
            self.__collect(event.writes)
        elif isinstance(event, TimeAdvanced):
            self.__publish(event.time, dispatcher)
