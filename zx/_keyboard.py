#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.


from __future__ import annotations

from ._data import DeviceSnapshot
from ._device import Device
from ._device import DeviceEvent
from ._device import Dispatcher
from ._device import InstallDeviceSnapshot
from ._device import ReadPort
from ._time import Time


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


# A transition of an emulated Spectrum key at exactly the given
# time.
class KeyStroke(DeviceEvent):
    def __init__(self, key: Key, pressed: bool, time: Time):
        self.key = key
        self.pressed = pressed
        self.time = time


# Builds the strokes typing the given keys: each key pressed and
# released in turn, combos like 'CS+SS' held together, integers
# typed as their digits. The transitions land at 0.1-second steps,
# the first one step after the given start time.
def make_key_strokes(*keys: int | str, start: Time) -> list[KeyStroke]:
    ids: list[str] = []
    for key in keys:
        if isinstance(key, int):
            ids.extend(str(key))
        else:
            ids.append(key)

    step = Time(1, ticks_per_second=10)
    time = start

    strokes = []
    for id in ids:
        combo = id.split('+')

        for i in combo:
            time = time + step
            strokes.append(KeyStroke(KEYS[i], pressed=True, time=time))

        for i in reversed(combo):
            time = time + step
            strokes.append(KeyStroke(KEYS[i], pressed=False, time=time))

    return strokes


class KeyboardSnapshot(DeviceSnapshot):
    active: bool | None

    def __init__(self, *, active: bool | None = None) -> None:
        super().__init__(active=active)


class Keyboard(Device, snapshot_type=KeyboardSnapshot):
    """The keyboard matrix as a function of time.

    A port read at time T returns the matrix state at T: all
    transitions at or before T applied. Reads come in time order,
    and a scheduled transition must be later than the last read,
    which would otherwise have sampled differently.
    """

    def __init__(self, *, active: bool = False) -> None:
        super().__init__(active=active)

        self.__state = [0xff] * 8

        # The time of the latest read; None before the first one.
        self.__last_read_time: Time | None = None

        # Strokes not yet in effect, in time order.
        self.__pending: list[KeyStroke] = []

    @classmethod
    def from_snapshot(cls, snapshot: DeviceSnapshot) -> Keyboard:
        assert isinstance(snapshot, KeyboardSnapshot)
        return cls(active=snapshot.active is True)

    def to_snapshot(self) -> KeyboardSnapshot | None:
        # Only the difference from the reset state is captured.
        if not self.active:
            return None

        return KeyboardSnapshot(active=True)

    def __apply(self, key: Key, pressed: bool) -> None:
        mask = 1 << key.port_bit

        if pressed:
            self.__state[key.address_line - 8] &= mask ^ 0xff
        else:
            self.__state[key.address_line - 8] |= mask

    def read_port(self, addr: int, time: Time) -> int:
        assert (self.__last_read_time is None or
                not (time < self.__last_read_time))
        self.__last_read_time = time

        i = 0
        for stroke in self.__pending:
            if time < stroke.time:
                break
            self.__apply(stroke.key, stroke.pressed)
            i += 1
        del self.__pending[:i]

        n = 0xff
        addr ^= 0xffff
        for line in range(8):
            if addr & (1 << (8 + line)):
                n &= self.__state[line]

        return n

    def __install_snapshot(self, s: DeviceSnapshot) -> None:
        assert isinstance(s, KeyboardSnapshot)

        # Whatever the snapshot does not mention is at reset.
        self.__state = [0xff] * 8
        self.__last_read_time = None
        self.__pending.clear()

        # Unmentioned activity means the reset state: inactive.
        self.active = s.active is True

    def on_event(self, event: DeviceEvent, devices: Dispatcher) -> None:
        if isinstance(event, InstallDeviceSnapshot):
            self.__install_snapshot(event.snapshot)
            return

        # An inactive keyboard is indistinguishable from an absent
        # one: it drives no input lines and consumes no strokes.
        if not self.active:
            return

        if isinstance(event, KeyStroke):
            assert (self.__last_read_time is None or
                    self.__last_read_time < event.time)
            assert (not self.__pending or
                    not (event.time < self.__pending[-1].time))
            self.__pending.append(event)
        elif isinstance(event, ReadPort):
            event.supply(self.read_port(event.addr, event.time))
