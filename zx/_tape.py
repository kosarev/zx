# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2019 Ivan Kosarev.
#   ivan@kosarev.info
#
#   Published under the MIT license.


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
