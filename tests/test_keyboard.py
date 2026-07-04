#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.


from zx._keyboard import KEYS
from zx._keyboard import Keyboard

# The documented port map: address line -> keys, lowest bit first.
PORT_MAP = {
    8: ('CAPS SHIFT', 'Z', 'X', 'C', 'V'),
    9: ('A', 'S', 'D', 'F', 'G'),
    10: ('Q', 'W', 'E', 'R', 'T'),
    11: ('1', '2', '3', '4', '5'),
    12: ('0', '9', '8', '7', '6'),
    13: ('P', 'O', 'I', 'U', 'Y'),
    14: ('ENTER', 'L', 'K', 'J', 'H'),
    15: ('BREAK SPACE', 'SYMBOL SHIFT', 'M', 'N', 'B')}


def test_matrix() -> None:
    for address_line, ids in PORT_MAP.items():
        for port_bit, id in enumerate(ids):
            key = KEYS[id]
            assert key.id == id
            assert key.address_line == address_line
            assert key.port_bit == port_bit


def test_aliases() -> None:
    assert KEYS['CS'] is KEYS['CAPS SHIFT']
    assert KEYS['SS'] is KEYS['SYMBOL SHIFT']
    assert KEYS['SPACE'] is KEYS['BREAK SPACE']


def test_port_reads() -> None:
    keyboard = Keyboard()

    # J sits on address line 14, bit 3; reading with A14 low
    # selects its half-row, any other line leaves it invisible.
    keyboard.handle_key_stroke(KEYS['J'], pressed=True)
    assert keyboard.read_port(0xbffe) == 0xff ^ (1 << 3)
    assert keyboard.read_port(0x7ffe) == 0xff

    keyboard.handle_key_stroke(KEYS['J'], pressed=False)
    assert keyboard.read_port(0xbffe) == 0xff
