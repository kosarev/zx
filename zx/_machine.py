# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2019 Ivan Kosarev.
#   ivan@kosarev.info
#
#   Published under the MIT license.


import struct, zx
from ._emulator import Spectrum48Base


class StateImage(object):
    def __init__(self, image):
        self._fields = {}
        self._image = image

    def define_fields(self, fields):
        self._fields.update(fields)

    def get(self, field_id):
        offset, format = self._fields[field_id]
        size = struct.calcsize(format)
        return struct.unpack(format, self._image[offset:offset + size])[0]

    def set(self, field_id, field_value):
        offset, format = self._fields[field_id]
        size = struct.calcsize(format)
        self._image[offset:offset + size] = struct.pack(format, field_value)


class ProcessorState(StateImage):
    _PROCESSOR_FIELDS = {
        'bc': (0, '<H'),
        'de': (2, '<H'),
        'hl': (4, '<H'),
        'af': (6, '<H'), 'f': (6, 'B'), 'a': (7, 'B'),
        'ix': (8, '<H'),
        'iy': (10, '<H'),

        'alt_bc': (12, '<H'),
        'alt_de': (14, '<H'),
        'alt_hl': (16, '<H'),
        'alt_af': (18, '<H'), 'alt_f': (18, 'B'), 'alt_a': (19, 'B'),

        'pc': (20, '<H'),
        'sp': (22, '<H'),
        'ir': (24, '<H'), 'r': (24, 'B'), 'i': (25, 'B'),
        'wz': (26, '<H'),

        'iff1': (28, 'B'),
        'iff2': (29, 'B'),
        'int_mode': (30, 'B'),
        'index_rp_kind': (31, 'B'),
    }

    def __init__(self, image):
        StateImage.__init__(self, image)
        self.define_fields(self._PROCESSOR_FIELDS)

    def get_bc(self):
        return self.get('bc')

    def get_de(self):
        return self.get('de')

    def get_hl(self):
        return self.get('hl')

    def get_a(self):
        return self.get('a')

    def get_f(self):
        return self.get('f')

    def get_ix(self):
        return self.get('ix')

    def get_iy(self):
        return self.get('iy')

    def get_alt_bc(self):
        return self.get('alt_bc')

    def get_alt_de(self):
        return self.get('alt_de')

    def get_alt_hl(self):
        return self.get('alt_hl')

    def get_alt_a(self):
        return self.get('alt_a')

    def get_alt_f(self):
        return self.get('alt_f')

    def get_alt_af(self):
        return self.get('alt_af')

    def get_pc(self):
        return self.get('pc')

    def set_pc(self, pc):
        self.set('pc', pc)

    def get_sp(self):
        return self.get('sp')

    def set_sp(self, sp):
        self.set('sp', sp)

    def get_i(self):
        return self.get('i')

    def get_r_reg(self):
        return self.get('r')

    def get_iff1(self):
        return self.get('iff1')

    def get_iff2(self):
        return self.get('iff2')

    def get_int_mode(self):
        return self.get('int_mode')

    def get_iregp_kind(self):
        n = self.get('index_rp_kind')
        return {0: 'hl', 1: 'ix', 2: 'iy'}[n]

    def install_snapshot(self, snapshot):
        assert isinstance(snapshot, zx.ProcessorSnapshot)
        for field, value in snapshot.items():
            if field != 'id':
                self.set(field, value)


class MemoryState(object):
    def __init__(self, image):
        self._memory_image = image

    def get_memory_block(self, addr, size):
        return self._memory_image[addr:addr + size]

    def set_memory_block(self, addr, block):
        self._memory_image[addr:addr + len(block)] = block

    def set_memory_blocks(self, blocks):
        for addr, block in blocks:
            self.set_memory_block(addr, block)

    def read8(self, addr):
        return self._memory_image[addr]

    def read16(self, addr):
        return zx.make16(hi=self.read8(addr + 1), lo=self.read8(addr))


class MachineState(ProcessorState, MemoryState):
    _MACHINE_FIELDS = {
        'ticks_since_int': (32, '<L'),
        'fetches_to_stop': (36, '<L'),
        'int_suppressed':  (40, 'B'),
        'int_after_ei_allowed': (41, 'B'),
        'border_color': (42, 'B'),
        'trace_enabled': (43, 'B'),
    }

    def __init__(self, machine_image, memory_image):
        ProcessorState.__init__(self, machine_image)
        MemoryState.__init__(self, memory_image)
        self.define_fields(self._MACHINE_FIELDS)

    def clone(self):
        return MachineState(self._image[:], self._memory_image[:])

    def is_suppressed_int(self):
        return bool(self.get('int_suppressed'))

    def suppress_int(self, suppress=True):
        self.set('int_suppressed', int(suppress))

    def allow_int_after_ei(self, allow=True):
        self.set('int_after_ei_allowed', int(allow))

    def get_fetches_limit(self):
        return self.get('fetches_to_stop')

    def set_fetches_limit(self, fetches_to_stop):
        self.set('fetches_to_stop', fetches_to_stop)

    def get_ticks_since_int(self):
        return self.get('ticks_since_int')

    def set_ticks_since_int(self, ticks):
        self.set('ticks_since_int', ticks)

    def get_border_color(self):
        return self.get('border_color')

    def set_border_color(self, color):
        self.set('border_color', color)

    def enable_trace(self, enable=True):
        self.set('trace_enabled', int(enable))

    def install_snapshot(self, snapshot):
        assert isinstance(snapshot, zx._MachineSnapshot)
        for field, value in snapshot.get_unified_snapshot().items():
            if field == 'processor_snapshot':
                ProcessorState.install_snapshot(self, value)
            elif field == 'memory_blocks':
                self.set_memory_blocks(value)
            else:
                self.set(field, value)


class Spectrum48(Spectrum48Base, MachineState):
    # Events.
    _NO_EVENTS         = 0
    _END_OF_FRAME      = 1 << 1
    _FETCHES_LIMIT_HIT = 1 << 3
    _BREAKPOINT_HIT    = 1 << 4

    # Memory marks.
    _NO_MARKS        = 0
    _BREAKPOINT_MARK = 1 << 0

    def __init__(self):
        self.machine_kind = 'ZX Spectrum 48K'
        MachineState.__init__(self, self.get_state_image(), self.get_memory())

        # Install ROM.
        self.set_memory_block(0x0000, zx.get_rom_image(self.machine_kind))

    def set_breakpoints(self, addr, size):
        self.mark_addrs(addr, size, self._BREAKPOINT_MARK)

    def set_breakpoint(self, addr):
        self.set_breakpoints(addr, 1)
