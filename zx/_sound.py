# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.

import ctypes
import numpy
import typing

from ._data import SoundPulses
from ._data import SpectrumModel
from ._device import Destroy
from ._device import Device
from ._device import DeviceEvent
from ._device import Dispatcher
from ._device import EmulatorReset
from ._device import NewSoundFrame
from ._device import OutputFrame
from ._device import SetFastForward


class PulseStream(object):
    def __init__(self, model: type[SpectrumModel]) -> None:
        self.__ticks_per_frame = model._TICKS_PER_FRAME

        # The last set sound level.
        self.__current_level = numpy.uint32(0)

        # The last pulse may happen past the end of the previous
        # frame. When this happens, we store the carried out pulse here.
        self.__carry_pulse: None | tuple[numpy.uint32, numpy.uint32] = None

    def reset(self) -> None:
        self.__current_level = numpy.uint32(0)
        self.__carry_pulse = None

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
        if len(ticks) == 0 or ticks[0] > 0:
            levels = numpy.insert(levels, 0, self.__current_level)
            ticks = numpy.insert(ticks, 0, 0)
        if ticks[-1] >= self.__ticks_per_frame:
            assert self.__carry_pulse is None
            self.__carry_pulse = ticks[-1] - self.__ticks_per_frame, levels[-1]
            ticks = numpy.delete(ticks, -1)
            levels = numpy.delete(levels, -1)
        if ticks[-1] < self.__ticks_per_frame - 1:
            levels = numpy.append(levels, levels[-1])
            ticks = numpy.append(ticks, self.__ticks_per_frame - 1)
        assert ticks[0] == 0 and ticks[-1] == self.__ticks_per_frame - 1

        self.__current_level = levels[-1]

        FRAMES_PER_SEC = 50  # TODO
        rate = self.__ticks_per_frame * FRAMES_PER_SEC
        return SoundPulses(rate, levels, ticks,
                           num_ticks=self.__ticks_per_frame)


class _PulseResampler(object):
    # The single stateful resampler of the mixed pulse stream.
    # Chunks of one stream cannot be resampled independently: the
    # fractional sample position and the averaging window carry
    # across chunk boundaries.

    # The number of upscaled samples averaged per output sample.
    # Averaging helps removing high-frequency noise in some
    # programs, e.g., the Wham! music editor.
    __UPSCALE = 10

    def __init__(self, output_rate: int) -> None:
        self.__output_rate = output_rate
        self.__source_rate: None | int = None

        # The finalised stream position, in source ticks.
        self.__num_ticks = 0

        # Upscaled samples of an incomplete averaging window. They
        # are not yet fully supported by finalised input — the next
        # chunk may still affect the output sample they belong to —
        # so they must not reach the sound card until completed.
        self.__carry: numpy.typing.NDArray[numpy.float64] = (
            numpy.zeros(0, dtype=numpy.float64))

    def feed(self, levels: numpy.typing.NDArray[numpy.float64],
             ticks: numpy.typing.NDArray[numpy.uint32],
             num_ticks: int, rate: int) -> (
                 numpy.typing.NDArray[numpy.float32]):
        # The source rate is a property of the stream, not of its
        # chunks.
        if self.__source_rate is None:
            self.__source_rate = rate
        assert rate == self.__source_rate

        # Chunks define their level over their whole span.
        assert len(ticks) > 0 and ticks[0] == 0

        N = self.__UPSCALE
        ratio = self.__output_rate * N / self.__source_rate

        # Upscaled-index boundaries of the level segments: each
        # transition and then the span end, all positioned on the
        # continuous stream timeline.
        begin = self.__num_ticks
        bounds = numpy.empty(len(ticks) + 1, dtype=numpy.int64)
        bounds[:-1] = ((begin + ticks) * ratio + 0.5).astype(numpy.int64)
        bounds[-1] = int((begin + num_ticks) * ratio + 0.5)

        upscaled = numpy.repeat(levels, numpy.diff(bounds))

        self.__num_ticks = begin + num_ticks

        # Emit only output samples whose averaging window is fully
        # supported by the finalised input; hold back the rest.
        upscaled = numpy.concatenate([self.__carry, upscaled])
        num_full = len(upscaled) // N * N
        self.__carry = upscaled[num_full:]

        samples: numpy.typing.NDArray[numpy.float32] = (
            upscaled[:num_full].reshape(-1, N).mean(
                axis=1, dtype=numpy.float32))
        return samples


class SoundDevice(Device):
    # TODO: Rename to output rate.
    __OUTPUT_FREQ = 44100

    def __init__(self) -> None:
        self.__frame_events: list[NewSoundFrame] = []
        self.__fast_forward = False
        self.__resampler = _PulseResampler(self.__OUTPUT_FREQ)

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

    # Mixing happens by time, in the pulse domain: the chunks of a
    # finality window all cover that window, so the mixed level
    # function changes at the union of their transition points.
    # Sequential-vs-simultaneous is encoded in the spans; no channel
    # identity is needed.
    def __mix_pulses(self, chunks: list[SoundPulses]) -> (
            tuple[numpy.typing.NDArray[numpy.float64],
                  numpy.typing.NDArray[numpy.uint32],
                  int, int]):
        assert len(chunks) > 0, 'TODO: Support having no sound channels!'

        num_ticks = chunks[0].num_ticks
        rate = chunks[0].rate
        for c in chunks:
            assert c.num_ticks == num_ticks
            assert c.rate == rate
            # Chunks define their level over their whole span.
            assert len(c.ticks) > 0 and c.ticks[0] == 0

        ticks = numpy.unique(
            numpy.concatenate([c.ticks for c in chunks]))

        mixed = numpy.zeros(len(ticks), dtype=numpy.float64)
        for c in chunks:
            # The level of the segment covering each union point.
            segments = numpy.searchsorted(c.ticks, ticks,
                                          side='right') - 1
            mixed += c.levels[segments]
        mixed /= len(chunks)

        return mixed, ticks, num_ticks, rate

    def __output_frame(self) -> None:
        if self.__fast_forward:
            self.__frame_events.clear()
            return

        chunks = [e.pulses for e in self.__frame_events]
        self.__frame_events.clear()

        levels, ticks, num_ticks, rate = self.__mix_pulses(chunks)
        samples = self.__resampler.feed(levels, ticks, num_ticks, rate)

        import sdl2.audio
        import ctypes
        while sdl2.audio.SDL_GetQueuedAudioSize(self.__device) > (
                self.__OUTPUT_FREQ // 50):
            sdl2.SDL_Delay(10)

        sdl2.audio.SDL_QueueAudio(
            self.__device,
            samples.ctypes.data_as(ctypes.c_void_p),
            len(samples) * 4)

    def on_event(self, event: DeviceEvent,
                 dispatcher: Dispatcher) -> None:
        if isinstance(event, EmulatorReset):
            self.__frame_events.clear()
            self.__resampler = _PulseResampler(self.__OUTPUT_FREQ)
        elif isinstance(event, NewSoundFrame):
            self.__new_sound_frame(event)
        elif isinstance(event, SetFastForward):
            if event.active:
                assert not self.__fast_forward
            self.__fast_forward = event.active
        elif isinstance(event, OutputFrame):
            self.__output_frame()
        elif isinstance(event, Destroy):
            self.__destroy()
