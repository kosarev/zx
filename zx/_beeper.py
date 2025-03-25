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
from ._device import HandlePortWrites
from ._device import Destroy


class Beeper(Device):
    __OUTPUT_FREQ = 44100

    def __init__(self) -> None:
        import sounddevice  # type: ignore[import-untyped]
        self.__start_level = numpy.float32(0)
        self.__start_tick = numpy.float32(0)
        self.__stream = sounddevice.OutputStream(channels=1,
                                                 samplerate=self.__OUTPUT_FREQ,
                                                 dtype=numpy.float32)
        self.__stream.start()

    def __destroy(self) -> None:
        self.__stream.close()

    def __handle_port_writes(
            self, writes: numpy.typing.NDArray[numpy.uint64]) -> None:
        # Filter writes to the 0xfe port.
        writes = numpy.frombuffer(writes, dtype=numpy.uint64)
        writes = writes[writes & 0xff == 0xfe]

        # Get EAR levels and their corresponding ticks.
        # TODO: Factor in EAR levels as well.
        EAR_BIT_POS = 4
        levels = ((writes >> (16 + EAR_BIT_POS)) & 0x1).astype(numpy.float32)
        ticks = (writes >> 32).astype(numpy.float32)

        # Extend the levels and ticks to cover the whole frame.
        TICKS_PER_FRAME = 69888  # TODO
        if len(ticks) == 0 or ticks[0] > self.__start_tick:
            levels = numpy.insert(levels, 0, self.__start_level)
            ticks = numpy.insert(ticks, 0, self.__start_tick)
        if ticks[-1] < TICKS_PER_FRAME:
            levels = numpy.append(levels, levels[-1])
            ticks = numpy.append(ticks, numpy.float32(TICKS_PER_FRAME))

        # Convert CPU ticks into sample indexes.
        # TODO: Should we instead produce samples for the CPU ticks and
        # then resample to the target sound frequency?
        FRAMES_PER_SEC = 50
        SAMPLES_PER_FRAME = self.__OUTPUT_FREQ / FRAMES_PER_SEC
        sample_indexes = ticks / (TICKS_PER_FRAME / SAMPLES_PER_FRAME)
        sample_indexes = (sample_indexes + 0.5).astype(numpy.int32)

        # Compute intervals between the samples, in ticks.
        counts = numpy.diff(sample_indexes)

        # Create an array of samples.
        samples = numpy.repeat(levels[:-1], counts)

        self.__stream.write(samples)

        self.__start_level = levels[-1]
        self.__start_tick = ticks[-1] - TICKS_PER_FRAME

    def on_event(self, event: DeviceEvent, devices: Dispatcher,
                 result: typing.Any) -> typing.Any:
        if isinstance(event, HandlePortWrites):
            if not event.fast_forward:
                self.__handle_port_writes(event.writes)
        elif isinstance(event, Destroy):
            self.__destroy()

        return result
