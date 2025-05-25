# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2025 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.

import ctypes
import numpy
import typing

from ._data import SoundPulses
from ._device import Device
from ._device import DeviceEvent
from ._device import Dispatcher
from ._device import NewSoundFrame
from ._device import OutputFrame
from ._device import Destroy


class PulseStream(object):
    def __init__(self) -> None:
        # The last set sound level.
        self.__current_level = numpy.uint32(0)

        # The last pulse may happen past the end of the previous
        # frame. When this happens, we store the carried out pulse here.
        self.__carry_pulse: None | tuple[numpy.uint32, numpy.uint32] = None

    def stream_frame(self, levels: numpy.typing.NDArray[numpy.uint32],
                     ticks: numpy.typing.NDArray[numpy.uint32]) -> SoundPulses:
        # Apply the carry pulse, if any.
        if self.__carry_pulse is not None:
            tick, level = self.__carry_pulse
            assert len(ticks) == 0 or tick < ticks[0]
            levels = numpy.insert(levels, 0, level)
            ticks = numpy.insert(ticks, 0, tick)
            self.__carry_pulse = None

        # Extend the levels and ticks to cover the frame exactly.
        TICKS_PER_FRAME = 69888  # TODO
        if len(ticks) == 0 or ticks[0] > 0:
            levels = numpy.insert(levels, 0, self.__current_level)
            ticks = numpy.insert(ticks, 0, 0)
        if ticks[-1] >= TICKS_PER_FRAME:
            assert self.__carry_pulse is None
            self.__carry_pulse = ticks[-1] - TICKS_PER_FRAME, levels[-1]
            ticks = numpy.delete(ticks, -1)
            levels = numpy.delete(levels, -1)
        if ticks[-1] < TICKS_PER_FRAME - 1:
            levels = numpy.append(levels, levels[-1])
            ticks = numpy.append(ticks, TICKS_PER_FRAME - 1)
        assert ticks[0] == 0 and ticks[-1] == TICKS_PER_FRAME - 1

        self.__current_level = levels[-1]

        FRAMES_PER_SEC = 50  # TODO
        rate = TICKS_PER_FRAME * FRAMES_PER_SEC
        return SoundPulses(rate, levels, ticks)


class SoundDevice(Device):
    # TODO: Rename to output rate.
    __OUTPUT_FREQ = 44100

    def __init__(self) -> None:
        self.__frame_events: list[NewSoundFrame] = []

        # TODO: Don't use SDL until we know we are actually
        # outputting sound via it. (The user may want to do something
        # else with the original or mixed samples, or may want some
        # custom some channel mixing.)
        import sdl2.audio  # type: ignore
        sdl2.SDL_Init(sdl2.SDL_INIT_AUDIO)

        spec = sdl2.audio.SDL_AudioSpec(
            freq=self.__OUTPUT_FREQ,
            aformat=sdl2.audio.AUDIO_F32,
            channels=1,
            samples=(self.__OUTPUT_FREQ // 50),  # TODO
            )

        self.__device = sdl2.audio.SDL_OpenAudioDevice(None, 0, spec, None, 0)

        # Start playing.
        # TODO: Delay until we actually have some audio to output?
        sdl2.audio.SDL_PauseAudioDevice(self.__device, 0)

    def __destroy(self) -> None:
        import sdl2.audio
        sdl2.audio.SDL_CloseAudioDevice(self.__device)

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
        assert len(samples) > 0, 'TODO: Support having no sound channels!'
        mixed: numpy.typing.NDArray[numpy.float32] = (
            numpy.sum(samples, axis=0) / len(samples))
        return mixed

    def __output_frame(self) -> None:
        samples = [self.__generate_samples(e) for e in self.__frame_events]
        self.__frame_events.clear()

        mixed_samples = self.__mix_channels(samples)

        import sdl2.audio
        import ctypes
        while sdl2.audio.SDL_GetQueuedAudioSize(self.__device) > (
                self.__OUTPUT_FREQ // 50):
            sdl2.SDL_Delay(10)

        sdl2.audio.SDL_QueueAudio(
            self.__device,
            mixed_samples.ctypes.data_as(ctypes.c_void_p),
            len(mixed_samples) * 4)

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
