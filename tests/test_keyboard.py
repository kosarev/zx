#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.


import zx
from zx._device import Dispatcher
from zx._device import InstallDeviceSnapshot
from zx._device import ReadPort
from zx._device import RunQuantum
from zx._keyboard import KEYS
from zx._keyboard import Keyboard
from zx._keyboard import KeyboardSnapshot
from zx._keyboard import KeyStroke
from zx._spectrum48 import Spectrum48MemoryMapping
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


def test_stroke_at_time_zero() -> None:
    keyboard = Keyboard()
    devices = Dispatcher([keyboard])

    # Before the first read, any time is schedulable, the very
    # start of time included.
    devices.notify(KeyStroke(KEYS['J'], pressed=True, time=at(0)))
    assert read(devices, halfrow_addr('J'), 0) == pressed_value('J')


def test_stroke_at_quantum_ceiling() -> None:
    # A quantum's ceiling is the first moment uncommitted everywhere,
    # so a stroke stamped there must always be admissible — including
    # when the quantum ends on the very instruction that reads the
    # keyboard, which happens when the tick budget expires inside it.
    core = zx.Core()
    keyboard = Keyboard()
    devices = Dispatcher([core, keyboard])

    # IN A,(0xFE); JR $-2 -- an endless keyboard read loop.
    core.pc = 0x8000
    core.write(Spectrum48MemoryMapping(), 0x8000, b'\xdb\xfe\x18\xfc')

    ticks_per_second = core.ticks_per_second

    # A budget expiring inside the 11-tick IN stops the quantum right
    # at its boundary, with the port read as the last thing committed.
    quantum = RunQuantum(stop_after=Time(core.tick_count + 5,
                                         ticks_per_second=ticks_per_second))
    devices.notify(quantum)
    assert quantum.advanced_ceiling is not None

    devices.notify(KeyStroke(KEYS['SPACE'], pressed=True,
                             time=quantum.advanced_ceiling))


def test_disabled_keyboard() -> None:
    # A disabled keyboard is indistinguishable from an absent one:
    # it does not drive the input lines.
    keyboard = Keyboard(disabled=True)
    devices = Dispatcher([keyboard])

    devices.notify(KeyStroke(KEYS['J'], pressed=True, time=at(2)))
    assert read(devices, halfrow_addr('J'), 3) == 0xff


def test_keyboard_snapshot() -> None:
    # A disabled keyboard is indistinguishable from an absent one,
    # so it captures as nothing.
    assert Keyboard(disabled=True).to_snapshot() is None

    keyboard = Keyboard()
    snapshot = keyboard.to_snapshot()
    assert snapshot is not None
    assert snapshot.disabled is None

    # Installing a snapshot brings the keyboard to the state the
    # snapshot describes; a pressed key does not survive it.
    devices = Dispatcher([keyboard], devices_by_id={'keyboard': keyboard})
    devices.notify(KeyStroke(KEYS['J'], pressed=True, time=at(2)))
    assert read(devices, halfrow_addr('J'), 3) == pressed_value('J')

    devices.notify(InstallDeviceSnapshot(KeyboardSnapshot()),
                   device='keyboard')
    assert read(devices, halfrow_addr('J'), 1) == 0xff

    devices.notify(InstallDeviceSnapshot(KeyboardSnapshot(disabled=True)),
                   device='keyboard')
    assert keyboard.disabled

    # A device snapshot that does not state the flag means the reset
    # state: not disabled.
    devices.notify(InstallDeviceSnapshot(KeyboardSnapshot()),
                   device='keyboard')
    assert not keyboard.disabled
