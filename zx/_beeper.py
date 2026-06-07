# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.

import numpy
import typing

from ._data import SpectrumModel
from ._device import Device
from ._device import DeviceEvent
from ._device import Dispatcher
from ._device import EmulatorReset
from ._device import NewPortWrites
from ._device import NewSoundPulses
from ._device import TimeAdvanced
from ._sound import PulseStream


class Beeper(Device):
    def __init__(self, model: type[SpectrumModel]) -> None:
        self.__stream = PulseStream(model)

        # The window start: the previous heartbeat's stamp.
        self.__cursor: None | int = None

        # EAR transitions collected since the cursor, with their
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
        cursor = self.__cursor
        self.__cursor = stamp

        # Resynchronise after construction or reset.
        if cursor is None:
            self.__levels.clear()
            self.__ticks.clear()
            return

        span = (stamp - cursor) % (1 << 32)
        if span == 0:
            return

        if self.__levels:
            levels = numpy.concatenate(self.__levels)
            ticks = numpy.concatenate(self.__ticks)
            self.__levels.clear()
            self.__ticks.clear()

            # Offsets within the window; uint32 arithmetic wraps.
            ticks = ticks - numpy.uint32(cursor & 0xffffffff)
        else:
            levels = numpy.zeros(0, dtype=numpy.uint32)
            ticks = numpy.zeros(0, dtype=numpy.uint32)

        pulses = self.__stream.stream_chunk(levels, ticks, span)
        dispatcher.notify(NewSoundPulses(pulses))

    def on_event(self, event: DeviceEvent, dispatcher: Dispatcher) -> None:
        if isinstance(event, EmulatorReset):
            self.__stream.reset()
            self.__cursor = None
            self.__levels.clear()
            self.__ticks.clear()
        elif isinstance(event, NewPortWrites):
            self.__collect(event.writes)
        elif isinstance(event, TimeAdvanced):
            self.__publish(event.tick_count, dispatcher)
