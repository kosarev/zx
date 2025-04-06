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
from ._device import Destroy


class Beeper(Device):
    __OUTPUT_FREQ = 44100

    def __init__(self) -> None:
        import sounddevice  # type: ignore[import-untyped]

        # The last set sound level.
        self.__current_level = numpy.float32(0)

        # The last port write may happen beyond the end of the previous
        # frame. When this happens, we store the carried out write here.
        self.__carry_write: None | tuple[numpy.float32, numpy.float32] = None

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
            ticks = numpy.append(ticks, numpy.float32(TICKS_PER_FRAME - 1))
        assert ticks[0] == 0 and ticks[-1] == TICKS_PER_FRAME - 1

        # Convert CPU ticks into an upscaled number of sample indexes.
        N = 10
        FRAMES_PER_SEC = 50
        SAMPLES_PER_FRAME = self.__OUTPUT_FREQ * N / FRAMES_PER_SEC
        sample_indexes = ticks / (TICKS_PER_FRAME / SAMPLES_PER_FRAME)
        sample_indexes = (sample_indexes + 0.5).astype(numpy.int32)

        # Compute intervals between the samples, in ticks.
        counts = numpy.diff(sample_indexes)

        # Create an array of samples.
        samples = numpy.repeat(levels[:-1], counts)

        # Downscale samples back to their intented rate by averaging
        # adjacent samples. This helps removing high-frequency noise in
        # some programs, e.g., the Wham! music editor.
        samples = samples.reshape(-1, N).mean(axis=1)

        self.__stream.write(samples)

        self.__current_level = levels[-1]

    def on_event(self, event: DeviceEvent, devices: Dispatcher,
                 result: typing.Any) -> typing.Any:
        if isinstance(event, EndOfFrame):
            if not event.fast_forward:
                self.__handle_port_writes(event.port_writes)
        elif isinstance(event, Destroy):
            self.__destroy()

        return result
