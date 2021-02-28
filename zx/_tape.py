# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2019 Ivan Kosarev.
#   ivan@kosarev.info
#
#   Published under the MIT license.


from ._device import Device
from ._device import EndOfFrame
from ._time import Time


def _get_pilot_pulses(pilot_tone_len,
                      pilot_pulse_len=2168):
    for _ in range(pilot_tone_len):
        yield pilot_pulse_len, ('PILOT',)


def _get_sync_pulses(first_sync_pulse_len=667,
                     second_sync_pulse_len=735):
    yield first_sync_pulse_len, ('FIRST_SYNC_PULSE',)
    yield second_sync_pulse_len, ('SECOND_SYNC_PULSE',)


def _get_data_bits(data):
    for byte in data:
        for i in range(8):
            yield (byte & (1 << (7 - i))) != 0


def get_data_pulses(data,
                    zero_bit_pulse_len=855,
                    one_bit_pulse_len=1710):

    for bit in _get_data_bits(data):
        pulse = ((one_bit_pulse_len, ('ONE_BIT',)) if bit else
                 (zero_bit_pulse_len, ('ZERO_BIT',)))
        yield pulse
        yield pulse


def get_block_pulses(data,
                     pilot_pulse_len=2168,
                     first_sync_pulse_len=667,
                     second_sync_pulse_len=735,
                     zero_bit_pulse_len=855,
                     one_bit_pulse_len=1710,
                     pilot_tone_len=None):
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


def tag_last_pulse(pulses):
    current_pulse = None
    for pulse in pulses:
        if current_pulse:
            yield current_pulse
        current_pulse = pulse

    if current_pulse:
        level, pulse, ids = current_pulse
        if 'END' not in ids:
            ids = tuple(list(ids) + ['END'])
            yield level, pulse, ids


class TapePlayer(Device):
    def __init__(self):
        self._is_paused = True
        self._pulses = None
        self._tick = 0
        self._level = False
        self._pulse = 0
        self._ticks_per_frame = 69888  # TODO
        self._time = Time()

    def is_paused(self):
        return self._is_paused

    def pause(self, is_paused=True):
        self._is_paused = is_paused

    def unpause(self):
        self.pause(is_paused=False)

    def toggle_pause(self):
        self.pause(not self.is_paused())

    def is_end(self):
        return self._pulses is None

    def get_time(self):
        return self._time

    def load_parsed_file(self, file):
        self._pulses = file.get_pulses()
        self._level = False
        self.pause()

    def load_tape(self, file):
        self.load_parsed_file(file)

    def get_level_at_frame_tick(self, tick):
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

    def skip_rest_of_frame(self):
        if self._tick < self._ticks_per_frame:
            self.get_level_at_frame_tick(self._ticks_per_frame)

        assert self._tick >= self._ticks_per_frame
        self._tick -= self._ticks_per_frame

    def on_event(self, event, devices, result):
        if isinstance(event, EndOfFrame):
            self.skip_rest_of_frame()
        return result
