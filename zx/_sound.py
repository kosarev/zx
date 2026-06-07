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
from ._device import NewSoundPulses
from ._device import QuantumRun
from ._device import SetFastForward
from ._device import TimeAdvanced


class PulseStream(object):
    def __init__(self, model: type[SpectrumModel]) -> None:
        # TODO: This is really the clock rate of the tick timeline.
        self.__rate = model._TICKS_PER_FRAME * 50

        # The last set sound level.
        self.__current_level = numpy.uint32(0)

    def reset(self) -> None:
        self.__current_level = numpy.uint32(0)

    def stream_chunk(self, levels: numpy.typing.NDArray[numpy.uint32],
                     ticks: numpy.typing.NDArray[numpy.uint32],
                     num_ticks: int) -> SoundPulses:
        assert num_ticks > 0

        # Chunks define their level over their whole span: the
        # running level carries forward to the chunk start.
        if len(ticks) == 0 or ticks[0] != 0:
            levels = numpy.insert(levels, 0, self.__current_level)
            ticks = numpy.insert(ticks, 0, 0)

        assert int(ticks[-1]) < num_ticks
        self.__current_level = levels[-1]

        return SoundPulses(self.__rate, levels, ticks,
                           num_ticks=num_ticks)


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
        self.__chunks: list[SoundPulses] = []
        self.__heartbeat: None | int = None
        self.__cursor: None | int = None
        self.__fast_forward = False
        self.__resampler = _PulseResampler(self.__OUTPUT_FREQ)

        # Produced samples awaiting delivery to the device.
        self.__pending: list[numpy.typing.NDArray[numpy.float32]] = []

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

    # Mixing happens by time, in the pulse domain: a chunk is
    # located by its publication context, so the chunks of a window
    # all cover exactly that window, and the mixed level function
    # changes at the union of their transition points. How emitters
    # agree to coexist is their concern; no channel identity is
    # needed.
    def __mix_pulses(self, chunks: list[SoundPulses], span: int) -> (
            tuple[numpy.typing.NDArray[numpy.float64],
                  numpy.typing.NDArray[numpy.uint32]]):
        for c in chunks:
            # A chunk covers exactly the window being closed and
            # defines its level over the whole of it.
            assert c.num_ticks == span
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

        return mixed, ticks

    # Consume on the dispatch following the heartbeat, by which
    # point the heartbeat's dispatch has provably completed and all
    # chunks of its window are in — regardless of device order.
    # Production only: the resampled samples go to the pending
    # buffer; output policy lives in __feed().
    def __consume(self) -> None:
        if self.__heartbeat is None:
            return
        stamp, self.__heartbeat = self.__heartbeat, None
        chunks, self.__chunks = self.__chunks, []

        # Resynchronise after construction or reset.
        if self.__cursor is None:
            self.__cursor = stamp
            return

        span = (stamp - self.__cursor) % (1 << 32)
        self.__cursor = stamp

        if self.__fast_forward or span == 0:
            return

        # With no emitters there is no stream.
        if len(chunks) == 0:
            return

        levels, ticks = self.__mix_pulses(chunks, span)
        samples = self.__resampler.feed(levels, ticks, span,
                                        chunks[0].rate)
        if len(samples):
            self.__pending.append(samples)

    # Output policy: push the pending samples to the device.
    # TODO: The wait goes away once emulation is gated on the queue
    # level (the 'held' state) and room is guaranteed by the gate.
    def __feed(self) -> None:
        if not self.__pending:
            return
        samples = numpy.concatenate(self.__pending)
        self.__pending.clear()

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
            self.__chunks.clear()
            self.__pending.clear()
            self.__heartbeat = None
            self.__cursor = None
            self.__resampler = _PulseResampler(self.__OUTPUT_FREQ)
        elif isinstance(event, NewSoundPulses):
            self.__chunks.append(event.pulses)
        elif isinstance(event, SetFastForward):
            if event.active:
                assert not self.__fast_forward
            self.__fast_forward = event.active
        elif isinstance(event, QuantumRun):
            self.__consume()
            self.__feed()
        elif isinstance(event, TimeAdvanced):
            self.__heartbeat = event.tick_count
        elif isinstance(event, Destroy):
            self.__destroy()
