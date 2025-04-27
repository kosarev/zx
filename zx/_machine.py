# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2021 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.


import enum
import typing
import types
from ._data import DataRecord
from ._data import MachineSnapshot
from ._device import DeviceEvent
from ._device import Dispatcher
from ._device import Destroy
from ._device import GetEmulationPauseState
from ._device import GetEmulationTime
from ._device import KeyStroke
from ._device import LoadFile
from ._device import PauseStateUpdated
from ._device import SaveSnapshot
from ._device import ToggleEmulationPause
from ._device import ToggleTapePause
from ._emulatorbase import _Spectrum48Base  # type: ignore
from ._except import EmulationExit, EmulatorException
from ._keyboard import KEYS
from ._rom import load_rom_image
from ._z80snapshot import Z80Snapshot


class RunEvents(enum.IntFlag):
    NO_EVENTS = 0
    END_OF_FRAME = 1 << 1
    FETCHES_LIMIT_HIT = 1 << 3
    BREAKPOINT_HIT = 1 << 4
    END_OF_TAPE = 1 << 5


class StateParser(object):
    def __init__(self, image: memoryview) -> None:
        self.__image = image
        self.__pos = 0

    @property
    def parsed_image(self) -> memoryview:
        return self.__image[:self.__pos]

    def read_bytes(self, size: int) -> memoryview:
        block = self.__image[self.__pos:self.__pos + size]
        self.__pos += size
        assert len(block) == size
        return block

    def parse8(self) -> memoryview:
        return self.read_bytes(1)

    def parse16(self) -> memoryview:
        return self.read_bytes(2)

    def parse32(self) -> memoryview:
        return self.read_bytes(4)


class Z80State(object):
    def __init__(self, image: memoryview) -> None:
        p = StateParser(image)
        self.__bc = p.parse16()
        self.__de = p.parse16()
        self.__hl = p.parse16()
        self.__af = p.parse16()
        self.__ix = p.parse16()
        self.__iy = p.parse16()
        self.__alt_bc = p.parse16()
        self.__alt_de = p.parse16()
        self.__alt_hl = p.parse16()
        self.__alt_af = p.parse16()
        self.__pc = p.parse16()
        self.__sp = p.parse16()
        self.__ir = p.parse16()
        self.__wz = p.parse16()
        self.__iff1 = p.parse8()
        self.__iff2 = p.parse8()
        self.__int_mode = p.parse8()
        self.__iregp_kind = p.parse8()

        self.image = p.parsed_image

    # TODO: Use a mix-in from the z80 module to implement these?
    @property
    def bc(self) -> int:
        return int.from_bytes(self.__bc, 'little')

    @bc.setter
    def bc(self, value: int) -> None:
        self.__bc[:] = value.to_bytes(2, 'little')

    @property
    def de(self) -> int:
        return int.from_bytes(self.__de, 'little')

    @de.setter
    def de(self, value: int) -> None:
        self.__de[:] = value.to_bytes(2, 'little')

    @property
    def hl(self) -> int:
        return int.from_bytes(self.__hl, 'little')

    @hl.setter
    def hl(self, value: int) -> None:
        self.__hl[:] = value.to_bytes(2, 'little')

    @property
    def af(self) -> int:
        return int.from_bytes(self.__af, 'little')

    @af.setter
    def af(self, value: int) -> None:
        self.__af[:] = value.to_bytes(2, 'little')

    @property
    def a(self) -> int:
        return self.__af[1]

    @property
    def f(self) -> int:
        return self.__af[0]

    @property
    def ix(self) -> int:
        return int.from_bytes(self.__ix, 'little')

    @ix.setter
    def ix(self, value: int) -> None:
        self.__ix[:] = value.to_bytes(2, 'little')

    @property
    def iy(self) -> int:
        return int.from_bytes(self.__iy, 'little')

    @iy.setter
    def iy(self, value: int) -> None:
        self.__iy[:] = value.to_bytes(2, 'little')

    @property
    def alt_bc(self) -> int:
        return int.from_bytes(self.__alt_bc, 'little')

    @alt_bc.setter
    def alt_bc(self, value: int) -> None:
        self.__alt_bc[:] = value.to_bytes(2, 'little')

    @property
    def alt_de(self) -> int:
        return int.from_bytes(self.__alt_de, 'little')

    @alt_de.setter
    def alt_de(self, value: int) -> None:
        self.__alt_de[:] = value.to_bytes(2, 'little')

    @property
    def alt_hl(self) -> int:
        return int.from_bytes(self.__alt_hl, 'little')

    @alt_hl.setter
    def alt_hl(self, value: int) -> None:
        self.__alt_hl[:] = value.to_bytes(2, 'little')

    @property
    def alt_af(self) -> int:
        return int.from_bytes(self.__alt_af, 'little')

    @alt_af.setter
    def alt_af(self, value: int) -> None:
        self.__alt_af[:] = value.to_bytes(2, 'little')

    @property
    def alt_a(self) -> int:
        return self.__alt_af[1]

    @property
    def alt_f(self) -> int:
        return self.__alt_af[0]

    @property
    def pc(self) -> int:
        return int.from_bytes(self.__pc, 'little')

    @pc.setter
    def pc(self, value: int) -> None:
        self.__pc[:] = value.to_bytes(2, 'little')

    @property
    def sp(self) -> int:
        return int.from_bytes(self.__sp, 'little')

    @sp.setter
    def sp(self, value: int) -> None:
        self.__sp[:] = value.to_bytes(2, 'little')

    @property
    def ir(self) -> int:
        return int.from_bytes(self.__ir, 'little')

    @ir.setter
    def ir(self, value: int) -> None:
        self.__ir[:] = value.to_bytes(2, 'little')

    @property
    def i(self) -> int:
        return self.__ir[1]

    @property
    def r(self) -> int:
        return self.__ir[0]

    @property
    def iff1(self) -> int:
        return bool(self.__iff1[0])

    @iff1.setter
    def iff1(self, value: int) -> None:
        self.__iff1[0] = value

    @property
    def iff2(self) -> int:
        return bool(self.__iff2[0])

    @iff2.setter
    def iff2(self, value: int) -> None:
        self.__iff2[0] = value

    @property
    def int_mode(self) -> int:
        return self.__int_mode[0]

    @int_mode.setter
    def int_mode(self, value: int) -> None:
        self.__int_mode[0] = value

    @property
    def iregp_kind(self) -> str:
        n = self.__iregp_kind[0]
        return {0: 'hl', 1: 'ix', 2: 'iy'}[n]

    @iregp_kind.setter
    def iregp_kind(self, value: int) -> None:
        self.__iregp_kind[0] = value


class MemoryState(object):
    def __init__(self, image: memoryview) -> None:
        assert len(image) == 0x10000
        self.__image = image
        self.image = self.__image

    def read(self, addr: int, size: int) -> bytes:
        return self.__image[addr:addr + size]

    def write(self, addr: int, block: bytes) -> None:
        self.__image[addr:addr + len(block)] = block

    def read8(self, addr: int) -> int:
        return self.__image[addr]

    def read16(self, addr: int) -> int:
        return int.from_bytes(self.read(addr, 2), 'little')


class MachineState(Z80State, MemoryState):
    image: memoryview

    def __init__(self, image: memoryview) -> None:
        p = StateParser(image)

        self.z80_image = p.read_bytes(32)
        Z80State.__init__(self, self.z80_image)

        self.__ticks_since_int = p.parse32()
        self.__fetches_to_stop = p.parse32()
        self.__events = p.parse32()
        self.__int_suppressed = p.parse8()
        self.__int_after_ei_allowed = p.parse8()
        self.__border_colour = p.parse8()
        self.__trace_enabled = p.parse8()

        self.memory_image = p.read_bytes(0x10000)
        MemoryState.__init__(self, self.memory_image)

        self.image = p.parsed_image

    @property
    def suppress_interrupts(self) -> bool:
        return bool(self.__int_suppressed[0])

    @suppress_interrupts.setter
    def suppress_interrupts(self, suppress: bool) -> None:
        self.__int_suppressed[0] = int(suppress)

    @property
    def allow_int_after_ei(self) -> bool:
        return bool(self.__int_after_ei_allowed[0])

    @allow_int_after_ei.setter
    def allow_int_after_ei(self, allow: bool) -> None:
        self.__int_after_ei_allowed[0] = int(allow)

    @property
    def fetches_limit(self) -> int:
        assert 0  # TODO
        # return self.get('fetches_to_stop')

    @fetches_limit.setter
    def fetches_limit(self, fetches_to_stop: int) -> None:
        self.__fetches_to_stop[:] = fetches_to_stop.to_bytes(4, 'little')

    # TODO: Can we do without this?
    def get_events(self) -> int:
        return int.from_bytes(self.__events, 'little')

    # TODO: Can we do without this?
    def set_events(self, events: int) -> None:
        self.__events[:] = events.to_bytes(4, 'little')

    # TODO: Can we do without this?
    def raise_events(self, events: int) -> None:
        self.set_events(self.get_events() | events)

    @property
    def ticks_since_int(self) -> int:
        return int.from_bytes(self.__ticks_since_int, 'little')

    @ticks_since_int.setter
    def ticks_since_int(self, ticks: int) -> None:
        self.__ticks_since_int[:] = ticks.to_bytes(4, 'little')

    @property
    def border_colour(self) -> int:
        return self.__border_colour[0]

    @border_colour.setter
    def border_colour(self, value: int) -> None:
        self.__border_colour[0] = value

    ''' TODO
    def enable_trace(self, enable=True):
        self.set('trace_enabled', int(enable))
    '''

    def install_snapshot(self, snapshot: MachineSnapshot) -> None:
        for field, value in snapshot.to_unified_snapshot():
            if field == 'memory_blocks':
                for addr, block in value:
                    self.write(addr, block)
            else:
                setattr(self, field, value)


# TODO: Combine with Emulator.
class Spectrum48(_Spectrum48Base, MachineState):  # type: ignore[misc]
    # Memory marks.
    __NO_MARKS = 0
    __BREAKPOINT_MARK = 1 << 0

    devices: Dispatcher

    def __init__(self) -> None:
        MachineState.__init__(self, self._get_state_view())

        # Install ROM.
        self.write(0x0000, load_rom_image('Spectrum48.rom'))

        self.__paused = False

    def __enter__(self) -> 'Spectrum48':
        return self

    def __exit__(self, xtype: None | type[BaseException],
                 value: None | BaseException,
                 traceback: None | types.TracebackType) -> None:
        self.devices.notify(Destroy())

    def stop(self) -> None:
        raise EmulationExit()

    @property
    def paused(self) -> bool:
        return self.__paused

    @paused.setter
    def paused(self, value: bool) -> None:
        self.__paused = value
        assert self.devices is not None
        self.devices.notify(PauseStateUpdated())

    def set_breakpoints(self, addr: int, size: int) -> None:
        self.mark_addrs(addr, size, self.__BREAKPOINT_MARK)

    def set_breakpoint(self, addr: int) -> None:
        self.set_breakpoints(addr, 1)

    def on_breakpoint(self) -> None:
        raise EmulatorException('Breakpoint triggered.')

    def on_event(self, event: DeviceEvent, devices: Dispatcher,
                 result: typing.Any) -> typing.Any:
        if isinstance(event, GetEmulationPauseState):
            return self.paused
        elif isinstance(event, GetEmulationTime):
            return self._emulation_time
        elif isinstance(event, KeyStroke):
            key = KEYS.get(event.id, None)
            if key:
                self.paused = False
                self._quit_playback_mode()
        elif isinstance(event, LoadFile):
            self._load_file(event.filename)
        elif isinstance(event, SaveSnapshot):
            self._save_snapshot_file(Z80Snapshot, event.filename)
        elif isinstance(event, ToggleEmulationPause):
            self.paused ^= True
        elif isinstance(event, ToggleTapePause):
            self._toggle_tape_pause()
        return result
