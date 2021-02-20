# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2021 Ivan Kosarev.
#   ivan@kosarev.info
#
#   Published under the MIT license.


import enum
from ._data import MachineSnapshot
from ._data import ProcessorSnapshot
from ._device import GetEmulationPauseState
from ._device import GetEmulationTime
from ._device import GetTapePlayerTime
from ._device import IsTapePlayerPaused
from ._device import KeyStroke
from ._device import LoadFile
from ._device import PauseStateUpdated
from ._device import ToggleEmulationPause
from ._device import ToggleTapePause
from ._emulatorbase import _Spectrum48Base
from ._except import EmulationExit
from ._keyboard import KEYS
from ._rom import get_rom_image
from ._utils import make16


class RunEvents(enum.IntFlag):
    NO_EVENTS = 0
    END_OF_FRAME = 1 << 1
    FETCHES_LIMIT_HIT = 1 << 3
    BREAKPOINT_HIT = 1 << 4
    END_OF_TAPE = 1 << 5


class _ImageParser(object):
    def __init__(self, image):
        self.__image = image
        self.__pos = 0

    @property
    def parsed_image(self):
        return self.__image[:self.__pos]

    def parse_block(self, size):
        block = self.__image[self.__pos:self.__pos + size]
        self.__pos += size
        assert len(block) == size
        return block

    def parse8(self):
        return self.parse_block(1)

    def parse16(self):
        return self.parse_block(2)

    def parse32(self):
        return self.parse_block(4)


def _make16(b0, b1):
    return b0 + (b1 << 8)


def _split16(n):
    return bytes(((n >> 0) & 0xff, (n >> 8) & 0xff))


def _make32(b0, b1, b2, b3):
    return b0 + (b1 << 8) + (b2 << 16) + (b3 << 24)


def _split32(n):
    return bytes(((n >> 0) & 0xff, (n >> 8) & 0xff,
                  (n >> 16) & 0xff, (n >> 23) & 0xff))


class Z80State(object):
    def __init__(self, image):
        p = _ImageParser(image)
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

    @property
    def bc(self):
        return _make16(*self.__bc)

    @bc.setter
    def bc(self, value):
        self.__bc[:] = _split16(value)

    @property
    def de(self):
        return _make16(*self.__de)

    @de.setter
    def de(self, value):
        self.__de[:] = _split16(value)

    @property
    def hl(self):
        return _make16(*self.__hl)

    @hl.setter
    def hl(self, value):
        self.__hl[:] = _split16(value)

    @property
    def af(self):
        return _make16(*self.__af)

    @af.setter
    def af(self, value):
        self.__af[:] = _split16(value)

    @property
    def ix(self):
        return _make16(*self.__ix)

    @ix.setter
    def ix(self, value):
        self.__ix[:] = _split16(value)

    @property
    def iy(self):
        return _make16(*self.__iy)

    @iy.setter
    def iy(self, value):
        self.__iy[:] = _split16(value)

    @property
    def alt_bc(self):
        return _make16(*self.__alt_bc)

    @alt_bc.setter
    def alt_bc(self, value):
        self.__alt_bc[:] = _split16(value)

    @property
    def alt_de(self):
        return _make16(*self.__alt_de)

    @alt_de.setter
    def alt_de(self, value):
        self.__alt_de[:] = _split16(value)

    @property
    def alt_hl(self):
        return _make16(*self.__alt_hl)

    @alt_hl.setter
    def alt_hl(self, value):
        self.__alt_hl[:] = _split16(value)

    @property
    def alt_af(self):
        return _make16(*self.__alt_af)

    @alt_af.setter
    def alt_af(self, value):
        self.__alt_af[:] = _split16(value)

    @property
    def pc(self):
        return _make16(*self.__pc)

    @pc.setter
    def pc(self, value):
        self.__pc[:] = _split16(value)

    @property
    def sp(self):
        return _make16(*self.__sp)

    @sp.setter
    def sp(self, value):
        self.__sp[:] = _split16(value)

    @property
    def ir(self):
        return _make16(*self.__ir)

    @ir.setter
    def ir(self, value):
        self.__ir[:] = _split16(value)

    @property
    def iff1(self):
        return bool(self.__iff1[0])

    @iff1.setter
    def iff1(self, value):
        self.__iff1[0] = value

    @property
    def iff2(self):
        return bool(self.__iff2[0])

    @iff2.setter
    def iff2(self, value):
        self.__iff2[0] = value

    @property
    def int_mode(self):
        return self.__int_mode[0]

    @int_mode.setter
    def int_mode(self, value):
        self.__int_mode[0] = value

    @property
    def iregp_kind(self):
        n = self.__iregp_kind[0]
        return {0: 'hl', 1: 'ix', 2: 'iy'}[n]

    @iregp_kind.setter
    def iregp_kind(self, value):
        self.__iregp_kind[0] = value

    def install_snapshot(self, snapshot):
        assert isinstance(snapshot, ProcessorSnapshot)
        for field, value in snapshot.items():
            if field != 'id':
                setattr(self, field, value)


class MemoryState(object):
    def __init__(self, image):
        assert len(image) == 0x10000
        self.__image = image
        self.image = self.__image

    def read(self, addr, size):
        return self.__image[addr:addr + size]

    def write(self, addr, block):
        self.__image[addr:addr + len(block)] = block

    def read8(self, addr):
        return self.__image[addr]

    def read16(self, addr):
        return _make16(*self.read(addr, 2))


class MachineState(Z80State, MemoryState):
    def __init__(self, image):
        p = _ImageParser(image)

        self.z80_image = p.parse_block(32)
        Z80State.__init__(self, self.z80_image)

        self.__ticks_since_int = p.parse32()
        self.__fetches_to_stop = p.parse32()
        self.__events = p.parse32()
        self.__int_suppressed = p.parse8()
        self.__int_after_ei_allowed = p.parse8()
        self.__border_color = p.parse8()
        self.__trace_enabled = p.parse8()

        self.memory_image = p.parse_block(0x10000)
        MemoryState.__init__(self, self.memory_image)

        self.image = p.parsed_image

    @property
    def suppress_interrupts(self):
        return bool(self.__is_suppressed_int[0])

    @suppress_interrupts.setter
    def suppress_interrupts(self, suppress):
        self.__int_suppressed[0] = int(suppress)

    @property
    def allow_int_after_ei(self):
        return bool(self.__int_after_ei_allowed[0])

    @allow_int_after_ei.setter
    def allow_int_after_ei(self, allow):
        self.__int_after_ei_allowed[0] = int(allow)

    @property
    def fetches_limit(self):
        return self.get('fetches_to_stop')

    @fetches_limit.setter
    def fetches_limit(self, fetches_to_stop):
        self.__fetches_to_stop[:] = _split32(fetches_to_stop)

    ''' TODO
    def get_events(self):
        return self.get('events')

    def set_events(self, events):
        self.set('events', events)

    def raise_events(self, events):
        self.set_events(self.get_events() | events)
    '''

    @property
    def ticks_since_int(self):
        return _make32(*self.__ticks_since_int)

    @ticks_since_int.setter
    def ticks_since_int(self, ticks):
        self.__ticks_since_int[:] = _split32(ticks)

    ''' TODO
    def get_border_color(self):
        return self.get('border_color')

    def set_border_color(self, color):
        self.set('border_color', color)

    def enable_trace(self, enable=True):
        self.set('trace_enabled', int(enable))
    '''

    def install_snapshot(self, snapshot):
        assert isinstance(snapshot, MachineSnapshot)
        for field, value in snapshot.get_unified_snapshot().items():
            if field == 'processor_snapshot':
                Z80State.install_snapshot(self, value)
            elif field == 'memory_blocks':
                for addr, block in value:
                    self.write(addr, block)
            else:
                setattr(self, field, value)


class Dispatcher(object):
    def __init__(self, devices=None):
        if devices is None:
            devices = []

        self.__devices = list(devices)

    def __iter__(self):
        yield from self.__devices

    # TODO: Since this now can return values, it needs a
    # different name.
    def notify(self, event):
        result = None
        for device in self:
            result = device.on_event(event, self, result)
        return result

    # TODO: Do that with events?
    def destroy(self):
        for device in self:
            device.destroy()


class Spectrum48(_Spectrum48Base, MachineState):
    # Memory marks.
    __NO_MARKS = 0
    __BREAKPOINT_MARK = 1 << 0

    def __init__(self):
        self.machine_kind = 'ZX Spectrum 48K'
        MachineState.__init__(self, self._get_state_view())

        # Install ROM.
        self.write(0x0000, get_rom_image(self.machine_kind))

        self.__paused = False

    def destroy(self):
        devices = self.devices
        self.devices = None

        if devices:
            devices.destroy()

    def __enter__(self):
        return self

    def __exit__(self, type, value, tb):
        self.destroy()

    def stop(self):
        raise EmulationExit()

    @property
    def paused(self):
        return self.__paused

    @paused.setter
    def paused(self, value):
        self.__paused = value
        self.devices.notify(PauseStateUpdated())

    def set_breakpoints(self, addr, size):
        self.mark_addrs(addr, size, self.__BREAKPOINT_MARK)

    def set_breakpoint(self, addr):
        self.set_breakpoints(addr, 1)

    def on_breakpoint(self):
        raise EmulatorException('Breakpoint triggered.')

    def on_event(self, event, devices, result):
        if isinstance(event, GetEmulationPauseState):
            return self.paused
        elif isinstance(event, GetEmulationTime):
            return self._emulation_time
        elif isinstance(event, GetTapePlayerTime):
            return self._tape_player.get_time()
        elif isinstance(event, IsTapePlayerPaused):
            return self._is_tape_paused()
        elif isinstance(event, KeyStroke):
            key = KEYS.get(event.id, None)
            if key:
                self.paused = False
                self._quit_playback_mode()
                self._handle_key_stroke(key, event.pressed)
        elif isinstance(event, LoadFile):
            self._load_file(event.filename)
        elif isinstance(event, ToggleEmulationPause):
            self.paused ^= True
        elif isinstance(event, ToggleTapePause):
            self._toggle_tape_pause()
        return result
