# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2019 Ivan Kosarev.
#   ivan@kosarev.info
#
#   Published under the MIT license.


def get_standard_pilot_pulses(is_header):
    pulse = 2168
    duration = 8063 if is_header else 3223
    for _ in range(duration):
        yield pulse


def get_standard_sync_pulses():
    yield 667
    yield 735


def _get_data_bits(data):
    for byte in data:
        for i in range(8):
            yield (byte & (1 << (7 - i))) != 0


def get_standard_data_pulses(data):
    for bit in _get_data_bits(data):
        pulse = 1710 if bit else 855
        yield pulse
        yield pulse


def get_standard_block_pulses(data):
    # Generate pilot tone.
    is_header = data[0] < 128
    for pulse in get_standard_pilot_pulses(is_header):
        yield pulse

    # Sync pulses.
    for pulse in get_standard_sync_pulses():
        yield pulse

    # Data.
    for pulse in get_standard_data_pulses(data):
        yield pulse
