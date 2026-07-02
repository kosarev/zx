#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.


import typing

import numpy

from ._binary import Bytes
from ._data import SoundFile
from ._data import SpectrumModel
from ._device import Device
from ._device import DeviceEvent
from ._device import Dispatcher
from ._device import GetTapePlayerTime
from ._device import IsTapePlayerPaused
from ._device import IsTapePlayerStopped
from ._device import LoadTape
from ._device import NewSoundPulses
from ._device import PauseUnpauseTape
from ._device import ReadPort
from ._device import ResetEmulator
from ._device import StopQuantum
from ._device import TapeStateUpdated
from ._device import TimeAdvanced
from ._sound import PulseStream
from ._time import Resolution
from ._time import Time

# Tape formats define pulse durations in ticks of the standard
# 3.5 MHz clock.
_TAPE_TICKS_PER_SECOND = 3_500_000


def _get_pilot_pulses(pilot_tone_len: int,
                      pilot_pulse_len: int = 2168) -> (
        typing.Iterable[tuple[int, tuple[str, ...]]]):
    for _ in range(pilot_tone_len):
        yield pilot_pulse_len, ('PILOT',)


def _get_sync_pulses(first_sync_pulse_len: int = 667,
                     second_sync_pulse_len: int = 735) -> (
        typing.Iterable[tuple[int, tuple[str, ...]]]):
    yield first_sync_pulse_len, ('FIRST_SYNC_PULSE',)
    yield second_sync_pulse_len, ('SECOND_SYNC_PULSE',)


def get_end_pulse(pulse_len: int = 945) -> (
        typing.Iterable[tuple[int, tuple[str, ...]]]):
    yield pulse_len, ('END_PULSE',)


def _get_data_bits(data: Bytes) -> typing.Iterable[bool]:
    for byte in data:
        for i in range(8):
            yield (byte & (1 << (7 - i))) != 0


def get_data_pulses(data: Bytes,
                    zero_bit_pulse_len: int = 855,
                    one_bit_pulse_len: int = 1710) -> (
        typing.Iterable[tuple[int, tuple[str, ...]]]):
    for bit in _get_data_bits(data):
        pulse = ((one_bit_pulse_len, ('ONE_BIT',)) if bit else
                 (zero_bit_pulse_len, ('ZERO_BIT',)))
        yield pulse
        yield pulse


def get_block_pulses(data: Bytes,
                     pilot_pulse_len: int = 2168,
                     first_sync_pulse_len: int = 667,
                     second_sync_pulse_len: int = 735,
                     zero_bit_pulse_len: int = 855,
                     one_bit_pulse_len: int = 1710,
                     pilot_tone_len: None | int = None) -> (
        typing.Iterable[tuple[int, tuple[str, ...]]]):
    # Generate pilot tone.
    if pilot_tone_len is None:
        is_header = data[0] < 128
        pilot_tone_len = 8063 if is_header else 3223

    for pulse in _get_pilot_pulses(pilot_tone_len):
        yield pulse

    # Sync pulses.
    for pulse in _get_sync_pulses(first_sync_pulse_len,
                                  second_sync_pulse_len):
        yield pulse

    # Data.
    for pulse in get_data_pulses(data,
                                 zero_bit_pulse_len,
                                 one_bit_pulse_len):
        yield pulse


def tag_last_pulse(pulses: typing.Iterable[tuple[bool, int,
                                                 tuple[str, ...]]]) -> (
        typing.Iterable[tuple[bool, int, tuple[str, ...]]]):
    current_pulse = None
    for pulse in pulses:
        if current_pulse:
            yield current_pulse
        current_pulse = pulse

    if current_pulse:
        level, duration, ids = current_pulse
        if 'END' not in ids:
            ids = (*ids, 'END')
            yield level, duration, ids


class TapePlayer(Device):
    _pulses: None | typing.Iterable[tuple[bool, int, tuple[str, ...]]]

    def __init__(self, model: type[SpectrumModel]) -> None:
        self._is_paused = True
        self._pulses = None
        self._tick = 0
        self._level = False
        self._pulse = 0
        self._time = Time(0, Resolution(_TAPE_TICKS_PER_SECOND))
        self.__audible_output = PulseStream(model._TICKS_PER_FRAME * 50)
        self.__audible_pulses: list[tuple[int, int]] = []

        # Unwrapping of 32-bit event stamps onto the tape's
        # monotonic internal timeline.
        self.__last_stamp: None | int = None
        self.__unwrapped = 0

        # The internal tick up to which sound has been published.
        self.__published_up_to_tick: None | int = None

    def __unwrap(self, stamp: int) -> int:
        if self.__last_stamp is None:
            # Anchor the internal timeline at the first stamp seen.
            self.__unwrapped = stamp
        else:
            self.__unwrapped += (stamp - self.__last_stamp) % (1 << 32)
        self.__last_stamp = stamp
        return self.__unwrapped

    def __is_paused(self) -> bool:
        return self._is_paused

    def __pause(self, is_paused: bool = True) -> None:
        self._is_paused = is_paused

    def __unpause(self) -> None:
        self.__pause(is_paused=False)

    def __toggle_pause(self) -> None:
        self.__pause(not self.__is_paused())

    def __is_end(self) -> bool:
        return self._pulses is None

    def __get_time(self) -> Time:
        return self._time

    def __load_parsed_file(self, file: SoundFile) -> None:
        self._pulses = file.get_pulses()
        self._level = False
        self.__pause()

    def __load_tape(self, file: SoundFile) -> None:
        self.__load_parsed_file(file)

    def __get_level_at_tick(self, tick: int) -> bool:
        assert tick >= self._tick, (self._tick, tick)

        # Get through the series of levels until we get the one at the
        # requested tick, which is when we are at the tick immediately
        # following it.
        target_tick = tick + 1
        while self._tick != target_tick:
            if self._is_paused:
                self._tick = target_tick
                continue

            # See if we already have a non-zero-length pulse.
            if self._pulse:
                self.__audible_pulses.append((self._level, self._tick))

                ticks_to_skip = min(self._pulse, target_tick - self._tick)
                self._pulse -= ticks_to_skip
                self._tick += ticks_to_skip
                self._time.advance(ticks_to_skip)
                continue

            # Get subsequent pulse, if any.
            new_pulse = None
            if self._pulses:
                new_pulse = next(iter(self._pulses), None)

            if new_pulse:
                # print(new_pulse)
                self._level, self._pulse, ids = new_pulse

                # The tape shall be considered stopped as soon as the last
                # pulse is fetched, and not on the next attempt to fetch a
                # pulse.
                if 'END' in ids:
                    self._pulses = None

                continue

            # Do nothing, if there are no more pulses available.
            self._pulses = None
            self._level = False
            self._tick = target_tick

        return self._level

    def __publish_chunk(self, tick: int, dispatcher: Dispatcher) -> None:
        # Catch the tape model up to the time-advanced position so
        # its sound advances even without port reads.
        if self._tick < tick:
            self.__get_level_at_tick(tick - 1)

        published_up_to = self.__published_up_to_tick
        self.__published_up_to_tick = tick

        # Resynchronise after construction or reset.
        if published_up_to is None:
            self.__audible_pulses = []
            return

        span = tick - published_up_to
        if span == 0:
            return

        # Play the tape sound for the user.
        levels, ticks = (zip(*self.__audible_pulses, strict=False)
                         if len(self.__audible_pulses) != 0 else ([], []))
        offsets = numpy.array(ticks, dtype=numpy.int64) - published_up_to
        pulses = self.__audible_output.stream_chunk(
            numpy.array(levels, dtype=numpy.uint32),
            offsets.astype(numpy.uint32),
            span)
        dispatcher.notify(NewSoundPulses(pulses))
        self.__audible_pulses = []

    def on_event(self, event: DeviceEvent,
                 dispatcher: Dispatcher) -> None:
        if isinstance(event, ResetEmulator):
            # Note that the internal timeline keeps running across
            # resets — only the transient sound state is discarded.
            self.__audible_pulses = []
            self.__audible_output.reset()
            self.__published_up_to_tick = None
        elif isinstance(event, TimeAdvanced):
            self.__publish_chunk(self.__unwrap(event.tick_count),
                                 dispatcher)
        elif isinstance(event, GetTapePlayerTime):
            event.time = self.__get_time()
        elif isinstance(event, ReadPort):
            if self._pulses is not None:
                tick = self.__unwrap(event.tick_count)
                if not self.__get_level_at_tick(tick):
                    event.supply(0xbf)  # EAR bit low when no tape signal

                # If that read exhausted the tape, ask the run to stop
                # at this exact tick (fires once -- the block is skipped
                # thereafter, since the tape is now ended).
                if self._pulses is None:
                    dispatcher.notify(StopQuantum())
        elif isinstance(event, IsTapePlayerPaused):
            event.paused |= self.__is_paused()
        elif isinstance(event, IsTapePlayerStopped):
            event.stopped |= self.__is_end()
        elif isinstance(event, LoadTape):
            self.__load_tape(event.file)
        elif isinstance(event, PauseUnpauseTape):
            self.__pause(event.pause)

            # TODO: Only notify if the state is actually changed.
            dispatcher.notify(TapeStateUpdated())
