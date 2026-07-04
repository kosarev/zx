#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.


from zx._device import Dispatcher
from zx._device import ReadPort
from zx._keyboard import KEYS
from zx._keyboard import Keyboard
from zx._keyboard import KeyStroke
from zx._time import Time

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


def at(tenths: int) -> Time:
    return Time(tenths, ticks_per_second=10)


def read(devices: Dispatcher, addr: int, tenths: int) -> int | None:
    port_read = ReadPort(addr, at(tenths))
    devices.notify(port_read)
    return port_read.value


# The port address selecting the key's half-row.
def halfrow_addr(key_id: str) -> int:
    return 0xfffe ^ (1 << KEYS[key_id].address_line)


# The value read from the key's half-row while the key is pressed.
def pressed_value(key_id: str) -> int:
    return 0xff ^ (1 << KEYS[key_id].port_bit)


def test_port_reads() -> None:
    keyboard = Keyboard()
    devices = Dispatcher([keyboard])

    devices.notify(KeyStroke(KEYS['J'], pressed=True, time=at(2)))
    devices.notify(KeyStroke(KEYS['J'], pressed=False, time=at(4)))

    assert read(devices, halfrow_addr('J'), 1) == 0xff
    assert read(devices, halfrow_addr('J'), 2) == pressed_value('J')
    assert read(devices, halfrow_addr('J'), 3) == pressed_value('J')
    assert read(devices, halfrow_addr('A'), 3) == 0xff
    assert read(devices, halfrow_addr('J'), 4) == 0xff


def test_live_strokes() -> None:
    keyboard = Keyboard()
    devices = Dispatcher([keyboard])

    assert read(devices, halfrow_addr('J'), 1) == 0xff

    # A live stroke takes effect at the next read, even at the same
    # time.
    devices.notify(KeyStroke(KEYS['J'], pressed=True, time=None))
    assert read(devices, halfrow_addr('J'), 1) == pressed_value('J')
