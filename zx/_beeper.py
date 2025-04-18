# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2025 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.

import numpy
import typing

from ._device import Device
from ._device import DeviceEvent
from ._device import Dispatcher
from ._device import EndOfFrame
from ._device import NewSoundFrame
from ._sound import PulseStream


class Beeper(Device):
    def __init__(self) -> None:
        self.__stream = PulseStream()

    def __handle_port_writes(
            self, writes: numpy.typing.NDArray[numpy.uint64],
            dispatcher: Dispatcher) -> None:
        # Filter writes to the 0xfe port.
        writes = numpy.frombuffer(writes, dtype=numpy.uint64)
        writes = writes[writes & 0xff == 0xfe]

        # Get EAR levels and their corresponding ticks.
        EAR_BIT_POS = 16 + 4
        levels = ((writes >> EAR_BIT_POS) & 0x1).astype(numpy.uint32)
        ticks = (writes >> 32).astype(numpy.uint32)

        pulses = self.__stream.stream_frame(levels, ticks)
        dispatcher.notify(NewSoundFrame('beeper', pulses))

    def on_event(self, event: DeviceEvent, dispatcher: Dispatcher,
                 result: typing.Any) -> typing.Any:
        if isinstance(event, EndOfFrame):
            self.__handle_port_writes(event.port_writes, dispatcher)

        return result
