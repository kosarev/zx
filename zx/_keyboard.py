# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2019 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.

import typing
from ._device import Device
from ._device import DeviceEvent
from ._device import KeyStroke
from ._device import ReadPort
from ._device import Dispatcher
from ._utils import tupilise


# TODO: Redesign.
class Key(object):
    def __init__(self, id: str, index: int) -> None:
        # TODO: Lowercase.
        self.ID = id
        self.INDEX = index  # Left to right, then top to bottom.
        halfrow_index = index // 5
        index_in_halfrow = index % 5
        is_leftside = halfrow_index % 2 == 0

        # Compute port address lines and bit positions.
        if is_leftside:
            self.ADDRESS_LINE = 11 - halfrow_index // 2
            self.PORT_BIT = index_in_halfrow
        else:
            self.ADDRESS_LINE = halfrow_index // 2 + 12
            self.PORT_BIT = 4 - index_in_halfrow


_KEY_IDS = [
    '1', '2', '3', '4', '5', '6', '7', '8', '9', '0',
    'Q', 'W', 'E', 'R', 'T', 'Y', 'U', 'I', 'O', 'P',
    'A', 'S', 'D', 'F', 'G', 'H', 'J', 'K', 'L', 'ENTER',
    ('CAPS SHIFT', 'CS'), 'Z', 'X', 'C', 'V',
    'B', 'N', 'M', ('SYMBOL SHIFT', 'SS'), ('BREAK SPACE', 'SPACE')]

KEYS = dict()
for index, ids in enumerate(_KEY_IDS):
    ids = tupilise(ids)
    id, *aliases = ids
    info = Key(id, index)
    for i in ids:
        KEYS[i] = info


class Keyboard(Device):
    _state = [0xff] * 8

    def read_port(self, addr: int) -> int:
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

    def handle_key_stroke(self, key_info: Key, pressed: bool) -> None:
        # print(key_info.id)
        addr_line = key_info.ADDRESS_LINE
        mask = 1 << key_info.PORT_BIT

        if pressed:
            self._state[addr_line - 8] &= mask ^ 0xff
        else:
            self._state[addr_line - 8] |= mask

    def on_event(self, event: DeviceEvent, devices: Dispatcher,
                 result: typing.Any) -> typing.Any:
        if isinstance(event, KeyStroke):
            key = KEYS.get(event.id, None)
            if key:
                self.handle_key_stroke(key, event.pressed)
        elif isinstance(event, ReadPort):
            result &= self.read_port(event.addr)
        return result
