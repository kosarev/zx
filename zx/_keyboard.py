# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2019 Ivan Kosarev.
#   ivan@kosarev.info
#
#   Published under the MIT license.


class KeyInfo(object):
    def __init__(self, id, index):
        self.ID = id
        self.INDEX = index  # Left to right, then top to bottom.
        self.HALFROW_INDEX = index // 5
        self.INDEX_IN_HALFROW = index % 5
        self.IS_LEFTSIDE = self.HALFROW_INDEX % 2 == 0
        self.IS_RIGHTSIDE = not self.IS_LEFTSIDE

        # Compute port address lines and bit positions.
        if self.IS_LEFTSIDE:
            self.ADDRESS_LINE = 11 - self.HALFROW_INDEX // 2
            self.PORT_BIT = self.INDEX_IN_HALFROW
        else:
            self.ADDRESS_LINE = self.HALFROW_INDEX // 2 + 12
            self.PORT_BIT = 4 - self.INDEX_IN_HALFROW


_KEY_IDS = [
    '1', '2', '3', '4', '5', '6', '7', '8', '9', '0',
    'Q', 'W', 'E', 'R', 'T', 'Y', 'U', 'I', 'O', 'P',
    'A', 'S', 'D', 'F', 'G', 'H', 'J', 'K', 'L', 'ENTER',
    'CAPS SHIFT', 'Z', 'X', 'C', 'V',
    'B', 'N', 'M', 'SYMBOL SHIFT', 'BREAK SPACE']

KEYS_INFO = dict()
for index, id in enumerate(_KEY_IDS):
    KEYS_INFO[id] = KeyInfo(id, index)


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
        # print(key_info.id)
        addr_line = key_info.ADDRESS_LINE
        mask = 1 << key_info.PORT_BIT

        if pressed:
            self._state[addr_line - 8] &= mask ^ 0xff
        else:
            self._state[addr_line - 8] |= mask
