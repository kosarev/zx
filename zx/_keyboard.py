#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.


from ._device import Device
from ._device import DeviceEvent
from ._device import Dispatcher
from ._device import ReadPort


# A key of the Spectrum's keyboard matrix: the port address line
# that selects its half-row and the bit it drives when read.
class Key:
    def __init__(self, id: str, address_line: int, port_bit: int) -> None:
        self.id = id
        self.address_line = address_line
        self.port_bit = port_bit


# The keyboard as laid out, a pair of half-rows per row, each with
# its port address line. Within a half-row, bits count from the
# outer edge of the keyboard inwards.
_ROWS = (
    ((11, ('1', '2', '3', '4', '5')), (12, ('6', '7', '8', '9', '0'))),
    ((10, ('Q', 'W', 'E', 'R', 'T')), (13, ('Y', 'U', 'I', 'O', 'P'))),
    ((9, ('A', 'S', 'D', 'F', 'G')), (14, ('H', 'J', 'K', 'L', 'ENTER'))),
    ((8, ('CAPS SHIFT', 'Z', 'X', 'C', 'V')),
     (15, ('B', 'N', 'M', 'SYMBOL SHIFT', 'BREAK SPACE'))))

_ALIASES = {
    'CS': 'CAPS SHIFT',
    'SS': 'SYMBOL SHIFT',
    'SPACE': 'BREAK SPACE'}

KEYS = {}
for (left_line, left_ids), (right_line, right_ids) in _ROWS:
    for port_bit, id in enumerate(left_ids):
        KEYS[id] = Key(id, left_line, port_bit)
    for port_bit, id in enumerate(reversed(right_ids)):
        KEYS[id] = Key(id, right_line, port_bit)
for alias, id in _ALIASES.items():
    KEYS[alias] = KEYS[id]


# A transition of an emulated Spectrum key.
class KeyStroke(DeviceEvent):
    def __init__(self, key: Key, pressed: bool):
        self.key = key
        self.pressed = pressed


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

    def handle_key_stroke(self, key: Key, pressed: bool) -> None:
        mask = 1 << key.port_bit

        if pressed:
            self._state[key.address_line - 8] &= mask ^ 0xff
        else:
            self._state[key.address_line - 8] |= mask

    def on_event(self, event: DeviceEvent, devices: Dispatcher) -> None:
        if isinstance(event, KeyStroke):
            self.handle_key_stroke(event.key, event.pressed)
        elif isinstance(event, ReadPort):
            event.supply(self.read_port(event.addr))
