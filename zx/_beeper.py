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
from ._pulses import Pulses


class Beeper(Device):
    def __init__(self) -> None:
        # The last set sound level.
        self.__current_level = numpy.float32(0)

        # The last port write may happen beyond the end of the previous
        # frame. When this happens, we store the carried out write here.
        self.__carry_write: None | tuple[numpy.float32, numpy.float32] = None

    def __handle_port_writes(
            self, writes: numpy.typing.NDArray[numpy.uint64],
            dispatcher: Dispatcher) -> None:
        # Filter writes to the 0xfe port.
        writes = numpy.frombuffer(writes, dtype=numpy.uint64)
        writes = writes[writes & 0xff == 0xfe]

        # Get EAR levels and their corresponding ticks.
        # TODO: Factor in EAR levels as well.
        EAR_BIT_POS = 4
        levels = ((writes >> (16 + EAR_BIT_POS)) & 0x1).astype(numpy.uint32)
        ticks = (writes >> 32).astype(numpy.uint32)

        # Apply the carry write, if any.
        if self.__carry_write is not None:
            tick, level = self.__carry_write
            assert len(ticks) == 0 or tick < ticks[0]
            levels = numpy.insert(levels, 0, level)
            ticks = numpy.insert(ticks, 0, tick)
            self.__carry_write = None

        # Extend the levels and ticks to cover the frame exactly.
        TICKS_PER_FRAME = 69888  # TODO
        if len(ticks) == 0 or ticks[0] > 0:
            levels = numpy.insert(levels, 0, self.__current_level)
            ticks = numpy.insert(ticks, 0, 0)
        if ticks[-1] >= TICKS_PER_FRAME:
            self.__carry_write = ticks[-1] - TICKS_PER_FRAME, levels[-1]
            ticks = numpy.delete(ticks, -1)
            levels = numpy.delete(levels, -1)
        if ticks[-1] < TICKS_PER_FRAME - 1:
            levels = numpy.append(levels, levels[-1])
            ticks = numpy.append(ticks, TICKS_PER_FRAME - 1)
        assert ticks[0] == 0 and ticks[-1] == TICKS_PER_FRAME - 1

        FRAMES_PER_SEC = 50  # TODO
        rate = TICKS_PER_FRAME * FRAMES_PER_SEC
        pulses = Pulses(rate, levels, ticks)
        dispatcher.notify(NewSoundFrame('beeper', pulses))

        self.__current_level = levels[-1]

    def on_event(self, event: DeviceEvent, dispatcher: Dispatcher,
                 result: typing.Any) -> typing.Any:
        if isinstance(event, EndOfFrame):
            self.__handle_port_writes(event.port_writes, dispatcher)

        return result
