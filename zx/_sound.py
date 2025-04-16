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
from ._device import NewSoundFrame
from ._device import OutputFrame
from ._device import Destroy


class SoundDevice(Device):
    # TODO: Use sounddevice.query_devices(sounddevice.default.device['output'])
    # TODO: Rename to output rate.
    __OUTPUT_FREQ = 44100

    def __init__(self) -> None:
        self.__frame_events: list[NewSoundFrame] = []

        # TODO: Don't use sounddevice until we know we are actually
        # outputting sound via it. (The user may want to do something
        # else with the original or mixed samples, or may want custom
        # some channel mixing.)
        import sounddevice  # type: ignore[import-untyped]

        self.__stream = sounddevice.OutputStream(channels=1,
                                                 samplerate=self.__OUTPUT_FREQ,
                                                 dtype=numpy.float32)
        self.__stream.start()

    def __destroy(self) -> None:
        self.__stream.close()

    def __new_sound_frame(self, frame_event: NewSoundFrame) -> None:
        self.__frame_events.append(frame_event)

    def __generate_samples(self, event: NewSoundFrame) -> (
            numpy.typing.NDArray[numpy.float32]):
        pulses = event.pulses
        levels, ticks = pulses.levels, pulses.ticks
        assert len(levels) == len(ticks)

        FRAMES_PER_SEC = 50  # TODO
        source_rate = pulses.rate
        source_num_samples_per_frame = int(source_rate / FRAMES_PER_SEC + 0.5)

        # Make sure we have source samples for the whole frame.
        assert ticks[0] == 0
        assert ticks[-1] == source_num_samples_per_frame - 1

        target_rate = self.__OUTPUT_FREQ
        target_num_samples_per_frame = int(target_rate / FRAMES_PER_SEC + 0.5)

        # Convert CPU ticks into an upscaled number of sample indexes.
        N = 10
        sample_indexes = ticks * (target_rate * N / source_rate)
        sample_indexes = (sample_indexes + 0.5).astype(numpy.int32)

        # Compute intervals between the samples, in source ticks.
        counts = numpy.diff(sample_indexes)

        # Create an array of samples.
        samples = numpy.repeat(levels[:-1], counts)

        # Downscale samples back to their intented rate by averaging
        # adjacent samples. This helps removing high-frequency noise in
        # some programs, e.g., the Wham! music editor.
        averaged_samples: numpy.typing.NDArray[numpy.float32] = (
            samples.reshape(-1, N).mean(axis=1, dtype=numpy.float32))

        return averaged_samples

    def __mix_channels(
            self, samples: list[numpy.typing.NDArray[numpy.float32]]) -> (
                numpy.typing.NDArray[numpy.float32]):
        assert len(samples) == 1, 'TODO: Support mixing multiple channels!'
        return samples[0]

    def __output_frame(self) -> None:
        samples = [self.__generate_samples(e) for e in self.__frame_events]
        self.__frame_events.clear()

        mixed_samples = self.__mix_channels(samples)
        self.__stream.write(mixed_samples)

    def on_event(self, event: DeviceEvent, dispatcher: Dispatcher,
                 result: typing.Any) -> typing.Any:
        if isinstance(event, NewSoundFrame):
            self.__new_sound_frame(event)
        elif isinstance(event, OutputFrame):
            if not event.fast_forward:
                self.__output_frame()
        elif isinstance(event, Destroy):
            self.__destroy()

        return result
