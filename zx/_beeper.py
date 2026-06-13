# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.

import typing

import numpy

from ._data import SpectrumModel
from ._device import Device
from ._device import DeviceEvent
from ._device import Dispatcher
from ._device import NewPortWrites
from ._device import NewSoundPulses
from ._device import ResetEmulator
from ._device import TimeAdvanced
from ._sound import PulseStream


class Beeper(Device):
    def __init__(self, model: type[SpectrumModel]) -> None:
        self.__stream = PulseStream(model)

        # The tick position up to which the beeper's sound has been
        # published.
        self.__published_up_to_tick: None | int = None

        # EAR transitions collected since then, with their
        # free-running tick stamps.
        self.__levels: list[numpy.typing.NDArray[numpy.uint32]] = []
        self.__ticks: list[numpy.typing.NDArray[numpy.uint32]] = []

    def __collect(self, writes: numpy.typing.NDArray[numpy.uint64]) -> None:
        # Filter writes to the 0xfe port.
        writes = writes[writes & numpy.uint64(0xff) == numpy.uint64(0xfe)]
        if len(writes) == 0:
            return

        # Get EAR levels and their tick stamps.
        EAR_BIT_POS = 16 + 4
        self.__levels.append(
            ((writes >> numpy.uint64(EAR_BIT_POS)) &
             numpy.uint64(1)).astype(numpy.uint32))
        self.__ticks.append(
            (writes >> numpy.uint64(32)).astype(numpy.uint32))

    def __publish(self, stamp: int, dispatcher: Dispatcher) -> None:
        published_up_to = self.__published_up_to_tick
        self.__published_up_to_tick = stamp

        # Resynchronise after construction or reset.
        if published_up_to is None:
            self.__levels.clear()
            self.__ticks.clear()
            return

        span = (stamp - published_up_to) % (1 << 32)
        if span == 0:
            return

        if self.__levels:
            levels = numpy.concatenate(self.__levels)
            ticks = numpy.concatenate(self.__ticks)
            self.__levels.clear()
            self.__ticks.clear()

            # Offsets within the published span; uint32 arithmetic
            # wraps.
            ticks = ticks - numpy.uint32(published_up_to & 0xffffffff)
        else:
            levels = numpy.zeros(0, dtype=numpy.uint32)
            ticks = numpy.zeros(0, dtype=numpy.uint32)

        pulses = self.__stream.stream_chunk(levels, ticks, span)
        dispatcher.notify(NewSoundPulses(pulses))

    def on_event(self, event: DeviceEvent, dispatcher: Dispatcher) -> None:
        if isinstance(event, ResetEmulator):
            self.__stream.reset()
            self.__published_up_to_tick = None
            self.__levels.clear()
            self.__ticks.clear()
        elif isinstance(event, NewPortWrites):
            self.__collect(event.writes)
        elif isinstance(event, TimeAdvanced):
            self.__publish(event.tick_count, dispatcher)
