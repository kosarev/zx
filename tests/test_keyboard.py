#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.


from zx._core import RunEvents
from zx._data import PortReadSeries
from zx._device import CollectPortReads
from zx._device import Dispatcher
from zx._device import InstallDeviceSnapshot
from zx._device import NewPortReads
from zx._device import RunQuantum
from zx._keyboard import KEYS
from zx._keyboard import Keyboard
from zx._keyboard import KeyboardSnapshot
from zx._keyboard import KeyStroke
from zx._spectrum48 import Spectrum48Core
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


# Queries the matrix directly: the keyboard as a function of time.
def read(keyboard: Keyboard, addr: int, tenths: int) -> int:
    return keyboard.read_port(addr, at(tenths))


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

    assert read(keyboard, halfrow_addr('J'), 1) == 0xff
    assert read(keyboard, halfrow_addr('J'), 2) == pressed_value('J')
    assert read(keyboard, halfrow_addr('J'), 3) == pressed_value('J')
    assert read(keyboard, halfrow_addr('A'), 3) == 0xff
    assert read(keyboard, halfrow_addr('J'), 4) == 0xff


def test_stroke_at_time_zero() -> None:
    keyboard = Keyboard()
    devices = Dispatcher([keyboard])

    # Before the first read, any time is schedulable, the very
    # start of time included.
    devices.notify(KeyStroke(KEYS['J'], pressed=True, time=at(0)))
    assert read(keyboard, halfrow_addr('J'), 0) == pressed_value('J')


def test_stroke_at_quantum_ceiling() -> None:
    # A quantum's ceiling is the first moment uncommitted everywhere,
    # so a stroke stamped there must always be admissible — including
    # when the quantum ends on the very instruction that reads the
    # keyboard, which happens when the tick budget expires inside it.
    core = Spectrum48Core()
    keyboard = Keyboard()
    devices = Dispatcher([core, keyboard])

    # IN A,(0xFE); JR $-2 -- an endless keyboard read loop.
    core.pc = 0x8000
    core.write(0x8000, b'\xdb\xfe\x18\xfc')

    ticks_per_second = core._ticks_per_second

    # A budget expiring inside the 11-tick IN stops the quantum right
    # at its boundary, with the port read as the last thing committed.
    quantum = RunQuantum(stop_after=Time(core.tick_count + 5,
                                         ticks_per_second=ticks_per_second))
    devices.notify(quantum)
    assert quantum.advanced_ceiling is not None

    devices.notify(KeyStroke(KEYS['SPACE'], pressed=True,
                             time=quantum.advanced_ceiling))


def test_keyboard_supplies_the_matrix() -> None:
    # One series per half-row, matching reads with the row's address
    # line and A0 both low, valued at the row's five bits with 1s in
    # the bits the row does not drive. A disabled keyboard supplies
    # nothing.
    keyboard = Keyboard()
    devices = Dispatcher([keyboard])
    devices.notify(KeyStroke(KEYS['A'], pressed=True, time=at(1)))

    collect = CollectPortReads(at(2), at(10))
    devices.notify(collect)
    assert len(collect.series) == 8

    masks = {series.addr_mask: series for series in collect.series}
    assert sorted(masks) == [(1 << (8 + row)) | 1 for row in range(8)]
    for series in collect.series:
        assert series.addr_value == 0x0000
        assert list(series.ticks) == [at(2).count]
        assert series.end_tick == at(10).count + 1

    # A is bit 0 of the half-row on address line 9.
    for row in range(8):
        series = masks[(1 << (8 + row)) | 1]
        assert list(series.values) == [0xfe if row == 1 else 0xff]

    collect = CollectPortReads(at(2), at(10))
    Dispatcher([Keyboard(disabled=True)]).notify(collect)
    assert collect.series == []


def test_keyboard_stroke_within_the_span() -> None:
    # A stroke past the floor becomes a transition within the
    # supplied span, at its exact moment.
    keyboard = Keyboard()
    devices = Dispatcher([keyboard])
    devices.notify(KeyStroke(KEYS['A'], pressed=True, time=at(5)))

    collect = CollectPortReads(at(2), at(10))
    devices.notify(collect)
    (series,) = [series for series in collect.series
                 if series.addr_mask == 0x0201]
    assert list(series.ticks) == [at(2).count, at(5).count]
    assert list(series.values) == [0xff, 0xfe]


def test_keyboard_read_from_samples() -> None:
    # A read of a half-row resolves from the supplied samples on the
    # C++ side.
    core = Spectrum48Core()
    keyboard = Keyboard()
    devices = Dispatcher([core, keyboard])

    # Select the A9 half-row: IN A, (0xfe) with A = 0xfd, reading
    # port 0xfdfe at tick 10.
    core.write(0x8000,
               b'\xdb\xfe'   # IN A, (0xfe)
               b'\x18\xfe')  # JR $
    core.pc = 0x8000
    core.a = 0xfd

    rate = core._ticks_per_second
    floor = Time(0, ticks_per_second=rate)
    devices.notify(KeyStroke(KEYS['A'], pressed=True, time=floor))

    collect = CollectPortReads(floor, Time(1000, ticks_per_second=rate))
    devices.notify(collect)
    devices.notify(NewPortReads(floor, collect.series))

    core._run(devices)
    assert core.a == 0xfe


def test_keyboard_samples_with_a_co_driver_series() -> None:
    # An empty series for the same reads -- a playing tape's --
    # makes them unresolvable from samples, whatever the keyboard
    # states: the read defers.
    core = Spectrum48Core()
    keyboard = Keyboard()
    devices = Dispatcher([core, keyboard])

    core.write(0x8000,
               b'\xdb\xfe'   # IN A, (0xfe)
               b'\x18\xfe')  # JR $
    core.pc = 0x8000
    core.a = 0xfd

    rate = core._ticks_per_second
    floor = Time(0, ticks_per_second=rate)
    devices.notify(KeyStroke(KEYS['A'], pressed=True, time=floor))

    collect = CollectPortReads(floor, Time(1000, ticks_per_second=rate))
    devices.notify(collect)
    collect.supply(PortReadSeries(addr_mask=0x0001, addr_value=0x0000))
    devices.notify(NewPortReads(floor, collect.series))

    events = RunEvents(core._run(devices))
    assert RunEvents.RETRY_INPUT in events
    assert core.pc == 0x8000
    assert core.a == 0xfd


def test_disabled_keyboard() -> None:
    # A disabled keyboard is indistinguishable from an absent one:
    # it consumes no strokes, so its matrix stays idle.
    keyboard = Keyboard(disabled=True)
    devices = Dispatcher([keyboard])

    devices.notify(KeyStroke(KEYS['J'], pressed=True, time=at(2)))
    assert read(keyboard, halfrow_addr('J'), 3) == 0xff


def test_keyboard_snapshot() -> None:
    # A disabled keyboard is indistinguishable from an absent one,
    # so it captures as nothing.
    assert Keyboard(disabled=True).take_snapshot() is None

    keyboard = Keyboard()
    snapshot = keyboard.take_snapshot()
    assert snapshot is not None
    assert snapshot.disabled is None

    # Installing a snapshot brings the keyboard to the state the
    # snapshot describes; a pressed key does not survive it.
    devices = Dispatcher([keyboard], devices_by_id={'keyboard': keyboard})
    devices.notify(KeyStroke(KEYS['J'], pressed=True, time=at(2)))
    assert read(keyboard, halfrow_addr('J'), 3) == pressed_value('J')

    devices.notify(InstallDeviceSnapshot(KeyboardSnapshot()),
                   device='keyboard')
    assert read(keyboard, halfrow_addr('J'), 1) == 0xff

    devices.notify(InstallDeviceSnapshot(KeyboardSnapshot(disabled=True)),
                   device='keyboard')
    assert keyboard.disabled

    # A device snapshot that does not state the flag means the reset
    # state: not disabled.
    devices.notify(InstallDeviceSnapshot(KeyboardSnapshot()),
                   device='keyboard')
    assert not keyboard.disabled
