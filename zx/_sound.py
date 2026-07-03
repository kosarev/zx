#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.


import math

import numpy

from ._data import SoundPulses
from ._device import DestroyEmulator
from ._device import Device
from ._device import DeviceEvent
from ._device import Dispatcher
from ._device import GetHoldState
from ._device import GetQuantumTimeLimit
from ._device import GetSettings
from ._device import NewSoundPulses
from ._device import ResetEmulator
from ._device import RunQuantum
from ._device import SetEmulationSpeed
from ._device import SetFastForward
from ._device import SetSettingValue
from ._device import SettingDescriptor
from ._device import SettingScope
from ._device import TimeAdvanced
from ._time import Time

# The initial speed: how fast emulated time runs relative to
# wallclock. The sound stream is the wallclock reference, so speed is
# purely the resampler ratio: at speed 2 a simulated span yields half
# the output samples, the sound queue fills half as fast, and the
# queued-audio backpressure lets emulation advance twice as far before
# holding. Pitch shifts with it, as on a real tape run fast. Changed at
# runtime via SetEmulationSpeed.
# Below realtime a whole frame would produce more audio than the
# latency budget in one step; SoundDevice handles that by reporting a
# sub-frame tick limit, so the quantum stays within the budget. Any
# positive speed is supported.
# TODO: Surface this through the GUI settings.
SPEED = 1.0
assert SPEED > 0


class PulseStream:
    def __init__(self) -> None:
        # The last set sound level.
        self.__current_level = numpy.uint32(0)

    def reset(self) -> None:
        self.__current_level = numpy.uint32(0)

    # The rate is that of the tick timeline the ticks count, in
    # ticks per second.
    def stream_chunk(self, levels: numpy.typing.NDArray[numpy.uint32],
                     ticks: numpy.typing.NDArray[numpy.uint32],
                     num_ticks: int, *, rate: int) -> SoundPulses:
        assert num_ticks > 0

        # Chunks define their level over their whole span: the
        # running level carries forward to the chunk start.
        if len(ticks) == 0 or ticks[0] != 0:
            levels = numpy.insert(levels, 0, self.__current_level)
            ticks = numpy.insert(ticks, 0, 0)

        # The level entering the next chunk is that of the last
        # transition, including one landing exactly on this chunk's
        # end.
        self.__current_level = levels[-1]

        # The span is half-open: a transition exactly on its end
        # belongs to the next chunk at offset 0, not to this one. This
        # happens when a port access falls on the very tick that closes
        # the chunk. Drop such transitions here; their level is carried
        # forward above, so the next chunk opens at it. Anything
        # strictly beyond the end would be a stamping bug.
        beyond = ticks[ticks >= num_ticks]
        assert (beyond == num_ticks).all(), (list(map(int, beyond)), num_ticks)

        keep = ticks < num_ticks
        levels = levels[keep]
        ticks = ticks[keep]

        return SoundPulses(rate, levels, ticks,
                           num_ticks=num_ticks)


class _PulseResampler:
    # The single stateful resampler of the mixed pulse stream.
    # Chunks of one stream cannot be resampled independently: the
    # fractional sample position and the averaging window carry
    # across chunk boundaries.

    # The number of upscaled samples averaged per output sample.
    # Averaging helps removing high-frequency noise in some
    # programs, e.g., the Wham! music editor.
    __UPSCALE = 10

    def __init__(self, output_rate: int, speed: float) -> None:
        self.__output_rate = output_rate
        self.__speed = speed
        self.__source_rate: None | int = None

        # The finalised stream position, in source ticks.
        self.__num_ticks = 0

        # Upscaled samples of an incomplete averaging window. They
        # are not yet fully supported by finalised input — the next
        # chunk may still affect the output sample they belong to —
        # so they must not reach the sound card until completed.
        self.__carry: numpy.typing.NDArray[numpy.float64] = (
            numpy.zeros(0, dtype=numpy.float64))

    def set_speed(self, speed: float) -> None:
        assert speed > 0
        self.__speed = speed

    def feed(self, levels: numpy.typing.NDArray[numpy.float64],
             ticks: numpy.typing.NDArray[numpy.int64],
             num_ticks: int, rate: int) -> (
                 numpy.typing.NDArray[numpy.float32]):
        # Chunks may come at any rates; the stream position refines
        # to the resolution representing them all exactly.
        if self.__source_rate is None:
            self.__source_rate = rate
        if rate != self.__source_rate:
            refined = math.lcm(self.__source_rate, rate)
            self.__num_ticks *= refined // self.__source_rate
            self.__source_rate = refined

        factor = self.__source_rate // rate
        if factor != 1:
            ticks = ticks * factor
            num_ticks *= factor

        # Chunks define their level over their whole span.
        assert len(ticks) > 0 and ticks[0] == 0

        # Speed compresses the source timeline: faster emulation packs
        # the same simulated span into fewer output samples.
        N = self.__UPSCALE
        ratio = self.__output_rate * N / (self.__source_rate * self.__speed)

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


# The sound device of the emulated machine. It mixes the pulse
# emitters and resamples their combined stream into output samples,
# and paces emulation against the amount of not-yet-played audio. The
# actual audio hardware is abstracted into a handful of device
# operations a backend subclass implements (SDLSound); the base does
# nothing for them, so a bare instance is a usable silent device that
# a test or API consumer can drive and observe by overriding _output().
class SoundDevice(Device):
    # The output sample rate produced. A backend must play at this rate.
    # TODO: Rename to output rate.
    _OUTPUT_FREQ = 44100

    # The discrete speed presets the speed setting offers: geometric
    # around 1x, the home speed. Fast-forward stays a separate gate,
    # not the top of this scale.
    __SPEED_CHOICES = (0.1, 0.25, 0.5, 1.0, 2.0, 4.0)

    __BYTES_PER_SAMPLE = 4

    # The discrete latency presets the latency setting offers, in
    # milliseconds of queued-but-unplayed audio, at or above the ~25ms
    # underrun floor.
    __LATENCY_CHOICES = (25, 50, 100, 200)

    # A nominal display refresh rate used only to keep slow-motion
    # quanta from advancing in over-large chunks. It is not the
    # screen's actual present rate — respecting that precisely is not
    # worth coupling the sound and screen devices; a decent assumed
    # value is enough for a cap.
    __ASSUMED_REFRESH_FPS = 50

    def __init__(self) -> None:
        self.__chunks: list[SoundPulses] = []

        # The stamp of the last TimeAdvanced notification, not yet
        # consumed.
        self.__last_time_advanced: None | Time = None

        # The time up to which sound has been consumed.
        self.__consumed_up_to: None | Time = None

        self.__fast_forward = False
        self.__speed = SPEED
        self.__resampler = _PulseResampler(self._OUTPUT_FREQ, self.__speed)

        # Produced samples awaiting delivery to the output.
        self.__pending: list[numpy.typing.NDArray[numpy.float32]] = []

        # The target amount of queued-but-unplayed audio, in
        # milliseconds: at once the underrun margin, the output latency
        # and the AV-skew bound. 50ms is imperceptible and absorbs
        # worst-case stalls (e.g. tape loading) on slower hosts.
        self.__latency_ms = 50

        self._open()

    # The audio-hardware operations. A backend subclass implements
    # them; the base does nothing, so it is a silent device.
    def _open(self) -> None:
        pass

    def _output(self, samples: numpy.typing.NDArray[numpy.float32]) -> None:
        pass

    def _queued_bytes(self) -> int:
        return 0

    def _close(self) -> None:
        pass

    # Mixing happens by time, in the pulse domain: the chunks
    # published for a span of time all cover exactly that span, each
    # in its own rate, so the mixed level function changes at the
    # union of their transition points on the common grid. How
    # emitters agree to coexist is their concern; no channel
    # identity is needed.
    def __mix_pulses(self, chunks: list[SoundPulses],
                     num_ticks: int, rate: int) -> (
            tuple[numpy.typing.NDArray[numpy.float64],
                  numpy.typing.NDArray[numpy.int64]]):
        scaled = []
        for c in chunks:
            # A chunk covers exactly the span being consumed and
            # defines its level over the whole of it.
            factor = rate // c.rate
            assert c.num_ticks * factor == num_ticks
            assert len(c.ticks) > 0 and c.ticks[0] == 0
            scaled.append(c.ticks.astype(numpy.int64) * factor)

        ticks = numpy.unique(numpy.concatenate(scaled))

        mixed = numpy.zeros(len(ticks), dtype=numpy.float64)
        for c, c_ticks in zip(chunks, scaled, strict=True):
            # The level of the segment covering each union point.
            segments = numpy.searchsorted(c_ticks, ticks,
                                          side='right') - 1
            mixed += c.levels[segments]
        mixed /= len(chunks)

        return mixed, ticks

    # Consume on the dispatch following a TimeAdvanced notification,
    # by which point its dispatch has provably completed and all
    # chunks published for the elapsed span are in — regardless of
    # device order. Production only: the resampled samples go to the
    # pending buffer; __feed() delivers them to the output.
    def __consume(self) -> None:
        if self.__last_time_advanced is None:
            return
        stamp = self.__last_time_advanced
        self.__last_time_advanced = None
        chunks, self.__chunks = self.__chunks, []

        # Resynchronise after construction or reset.
        if self.__consumed_up_to is None:
            self.__consumed_up_to = stamp
            return

        consumed_up_to = self.__consumed_up_to
        self.__consumed_up_to = stamp

        span = stamp - consumed_up_to

        if self.__fast_forward or span.count == 0:
            return

        # With no emitters there is no stream.
        if len(chunks) == 0:
            return

        # Bring the chunks and the span to one resolution.
        rate = span.ticks_per_second
        for c in chunks:
            rate = math.lcm(rate, c.rate)
        num_ticks = span.count * (rate // span.ticks_per_second)

        levels, ticks = self.__mix_pulses(chunks, num_ticks, rate)
        samples = self.__resampler.feed(levels, ticks, num_ticks, rate)
        if len(samples):
            self.__pending.append(samples)

    # Deliver the pending samples to the output, unconditionally. The
    # output queue is unbounded, so nothing needs to fit; the amount
    # of queued audio stays bounded because emulation does not
    # advance while it is above the threshold, so it never exceeds
    # the threshold plus one quantum's worth of samples. The sound
    # device never waits.
    def __feed(self) -> None:
        if not self.__pending:
            return
        samples = numpy.concatenate(self.__pending)
        self.__pending.clear()

        self._output(samples)

    # The queued-audio target in bytes, derived from the latency
    # setting.
    def __max_queued_bytes(self) -> int:
        return (round(self._OUTPUT_FREQ * self.__latency_ms / 1000) *
                self.__BYTES_PER_SAMPLE)

    # Emulation should not advance while the amount of queued audio
    # is above the limit; the time for the excess to play out is
    # exactly computable.
    def __answer_hold(self, event: GetHoldState) -> None:
        if self.__fast_forward:
            return

        queued = self._queued_bytes()
        max_queued = self.__max_queued_bytes()
        if queued > max_queued:
            event.hold(wake_in=(queued - max_queued) /
                       (self.__BYTES_PER_SAMPLE * self._OUTPUT_FREQ))

    # Cap how much output audio a single quantum may produce below
    # realtime, where a whole-frame quantum would otherwise make far
    # more than makes sense in one step (output audio per quantum =
    # emulated time / speed). Two bounds, the smaller winning:
    #  - the latency budget, so the queue does not swing past its
    #    target and the latency setting keeps meaning something;
    #  - a nominal display refresh, so the picture advances in small,
    #    frequent steps and slow motion stays smooth rather than
    #    jumping in large chunks.
    # The requested stop is the consumed-up-to time plus the span
    # these bounds allow. The span comes from wallclock amounts, so
    # it is approximate by nature and rounding it is fine. At or
    # above realtime it exceeds a frame, so the frame end applies
    # first and nothing changes — hence we only report a limit below
    # realtime.
    def __report_time_limit(self, event: GetQuantumTimeLimit) -> None:
        if self.__fast_forward or self.__speed >= 1.0:
            return

        # No time observed yet, so nothing to anchor the span to.
        if self.__consumed_up_to is None:
            return

        latency_seconds = self.__latency_ms / 1000
        max_output_seconds = min(latency_seconds,
                                 1.0 / self.__ASSUMED_REFRESH_FPS)
        rate = self.__consumed_up_to.ticks_per_second
        span = max(1, round(max_output_seconds * self.__speed * rate))
        event.stop_after(self.__consumed_up_to +
                         Time(span, ticks_per_second=rate))

    # The device owns the speed (resampler ratio) and latency
    # (queued-audio target) settings.
    def __report_settings(self, event: GetSettings) -> None:
        event.add_settings(
            SettingDescriptor(
                id='speed', scope=SettingScope.HOST, label='Speed',
                choices=self.__SPEED_CHOICES, current=self.__speed),
            SettingDescriptor(
                id='latency', scope=SettingScope.HOST,
                label='Sound latency (ms)',
                choices=self.__LATENCY_CHOICES, current=self.__latency_ms))

    def __apply_speed(self, speed: float) -> None:
        self.__speed = speed
        self.__resampler.set_speed(speed)

    def on_event(self, event: DeviceEvent,
                 dispatcher: Dispatcher) -> None:
        if isinstance(event, ResetEmulator):
            self.__chunks.clear()
            self.__pending.clear()
            self.__last_time_advanced = None
            self.__consumed_up_to = None
            self.__resampler = _PulseResampler(
                self._OUTPUT_FREQ, self.__speed)
        elif isinstance(event, NewSoundPulses):
            self.__chunks.append(event.pulses)
        elif isinstance(event, SetFastForward):
            if event.active:
                assert not self.__fast_forward
            self.__fast_forward = event.active
        elif isinstance(event, SetEmulationSpeed):
            self.__apply_speed(event.speed)
        elif isinstance(event, SetSettingValue):
            if event.id == 'speed':
                self.__apply_speed(float(event.value))
            elif event.id == 'latency':
                self.__latency_ms = int(event.value)
        elif isinstance(event, RunQuantum):
            self.__consume()
            self.__feed()
        elif isinstance(event, TimeAdvanced):
            self.__last_time_advanced = event.time
        elif isinstance(event, GetHoldState):
            self.__answer_hold(event)
        elif isinstance(event, GetQuantumTimeLimit):
            self.__report_time_limit(event)
        elif isinstance(event, GetSettings):
            self.__report_settings(event)
        elif isinstance(event, DestroyEmulator):
            self._close()


# The audio hardware, backed by SDL. It only implements the device
# operations; all sound logic lives in the base SoundDevice.
class SDLSound(SoundDevice):
    def _open(self) -> None:
        # TODO: Don't use SDL until we know we are actually
        # outputting sound via it. (The user may want to do something
        # else with the original or mixed samples, or may want some
        # custom some channel mixing.)
        import sdl2.audio  # type: ignore[import-untyped]
        sdl2.SDL_Init(sdl2.SDL_INIT_AUDIO)

        spec = sdl2.audio.SDL_AudioSpec(
            freq=self._OUTPUT_FREQ,
            aformat=sdl2.audio.AUDIO_F32,
            channels=1,
            samples=(self._OUTPUT_FREQ // 50),  # TODO
            )

        self.__device = sdl2.audio.SDL_OpenAudioDevice(None, 0, spec, None, 0)

        # Start playing.
        # TODO: Delay until we actually have some audio to output?
        sdl2.audio.SDL_PauseAudioDevice(self.__device, 0)

    def _output(self, samples: numpy.typing.NDArray[numpy.float32]) -> None:
        import ctypes

        import sdl2.audio
        sdl2.audio.SDL_QueueAudio(
            self.__device,
            samples.ctypes.data_as(ctypes.c_void_p),
            samples.nbytes)

    def _queued_bytes(self) -> int:
        import sdl2.audio
        queued: int = sdl2.audio.SDL_GetQueuedAudioSize(self.__device)
        return queued

    def _close(self) -> None:
        import sdl2.audio
        sdl2.audio.SDL_CloseAudioDevice(self.__device)
