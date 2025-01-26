# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2019 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.


import typing
from ._binary import Bytes
from ._data import SoundFile
from ._device import Device
from ._device import DeviceEvent
from ._device import Dispatcher
from ._device import EndOfFrame
from ._device import GetTapeLevel
from ._device import GetTapePlayerTime
from ._device import IsTapePlayerPaused
from ._device import IsTapePlayerStopped
from ._device import LoadTape
from ._device import PauseUnpauseTape
from ._device import TapeStateUpdated
from ._time import Time


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
            ids = tuple(list(ids) + ['END'])
            yield level, duration, ids


class TapePlayer(Device):
    _pulses: None | typing.Iterable[tuple[bool, int, tuple[str, ...]]]

    def __init__(self) -> None:
        self._is_paused = True
        self._pulses = None
        self._tick = 0
        self._level = False
        self._pulse = 0
        self._ticks_per_frame = 69888  # TODO
        self._time = Time()

    def is_paused(self) -> bool:
        return self._is_paused

    def pause(self, is_paused: bool = True) -> None:
        self._is_paused = is_paused

    def unpause(self) -> None:
        self.pause(is_paused=False)

    def toggle_pause(self) -> None:
        self.pause(not self.is_paused())

    def is_end(self) -> bool:
        return self._pulses is None

    def get_time(self) -> Time:
        return self._time

    def load_parsed_file(self, file: SoundFile) -> None:
        self._pulses = file.get_pulses()
        self._level = False
        self.pause()

    def load_tape(self, file: SoundFile) -> None:
        self.load_parsed_file(file)

    def get_level_at_frame_tick(self, tick: int) -> bool:
        assert self._tick <= tick, (self._tick, tick)

        while self._tick < tick:
            if self._is_paused:
                self._tick = tick
                continue

            # See if we already have a non-zero-length pulse.
            if self._pulse:
                ticks_to_skip = min(self._pulse, tick - self._tick)
                self._pulse -= ticks_to_skip
                self._tick += ticks_to_skip
                self._time.advance(ticks_to_skip /
                                   (self._ticks_per_frame * 50))
                continue

            # Get subsequent pulse, if any.
            new_pulse = None
            if self._pulses:
                for new_pulse in self._pulses:
                    break

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
            self._tick = tick

        return self._level

    def skip_rest_of_frame(self) -> None:
        if self._tick < self._ticks_per_frame:
            self.get_level_at_frame_tick(self._ticks_per_frame)

        assert self._tick >= self._ticks_per_frame
        self._tick -= self._ticks_per_frame

    def on_event(self, event: DeviceEvent, devices: Dispatcher,
                 result: typing.Any) -> typing.Any:
        if isinstance(event, EndOfFrame):
            self.skip_rest_of_frame()
        elif isinstance(event, GetTapePlayerTime):
            return self.get_time()
        elif isinstance(event, GetTapeLevel):
            return self.get_level_at_frame_tick(event.frame_tick)
        elif isinstance(event, IsTapePlayerPaused):
            return self.is_paused()
        elif isinstance(event, IsTapePlayerStopped):
            return self.is_end()
        elif isinstance(event, LoadTape):
            self.load_tape(event.file)
        elif isinstance(event, PauseUnpauseTape):
            self.pause(event.pause)

            # TODO: Only notify if the state is actually changed.
            devices.notify(TapeStateUpdated())

        return result
