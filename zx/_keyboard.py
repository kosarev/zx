# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2019 Ivan Kosarev.
#   ivan@kosarev.info
#
#   Published under the MIT license.


KEYS_INFO = dict()

# Generate layout-related information.
layout = ['1', '2', '3', '4', '5', '6', '7', '8', '9', '0',
          'Q', 'W', 'E', 'R', 'T', 'Y', 'U', 'I', 'O', 'P',
          'A', 'S', 'D', 'F', 'G', 'H', 'J', 'K', 'L', 'ENTER',
          'CAPS SHIFT', 'Z', 'X', 'C', 'V', 'B', 'N', 'M', 'SYMBOL SHIFT',
          'BREAK SPACE']
for n, id in enumerate(layout):
    key = KEYS_INFO.setdefault(id, dict())
    key['id'] = id
    key['number'] = n  # Left to right, then top to bottom.
    key['halfrow_number'] = n // 5
    key['pos_in_halfrow'] = n % 5
    key['is_leftside'] = key['halfrow_number'] % 2 == 0
    key['is_rightside'] = not key['is_leftside']

# Compute port address lines and bit positions.
for id, key in KEYS_INFO.items():
    if key['is_leftside']:
        key['address_line'] = 11 - key['halfrow_number'] // 2
        key['port_bit'] = key['pos_in_halfrow']
    else:
        key['address_line'] = key['halfrow_number'] // 2 + 12
        key['port_bit'] = 4 - key['pos_in_halfrow']


class KeyboardState(object):
    _state = [0xff] * 8

    def read_port(self, addr):
        n = 0xff
        addr ^= 0xffff

        if addr & (1 << 8):
            n &= self._state[0]
        if addr & (1 << 9):
            n &= self._state[1]
        if addr & (1 << 10):
            n &= self._state[2]
        if addr & (1 << 11):
            n &= self._state[3]
        if addr & (1 << 12):
            n &= self._state[4]
        if addr & (1 << 13):
            n &= self._state[5]
        if addr & (1 << 14):
            n &= self._state[6]
        if addr & (1 << 15):
            n &= self._state[7]

        return n

    def handle_key_stroke(self, key_info, pressed):
        # print(key_info['id'])
        addr_line = key_info['address_line']
        mask = 1 << key_info['port_bit']

        if pressed:
            self._state[addr_line - 8] &= mask ^ 0xff
        else:
            self._state[addr_line - 8] |= mask
