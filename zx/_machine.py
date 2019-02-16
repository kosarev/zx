# -*- coding: utf-8 -*-

import struct, zx
from ._emulator import Spectrum48Base


class StateImage(object):
    def __init__(self, fields, image):
        self._fields = fields
        self._image = image

    def get(self, field_id):
        offset, format = self._fields[field_id]
        size = struct.calcsize(format)
        return struct.unpack(format, self._image[offset:offset + size])[0]

    def set(self, field_id, field_value):
        offset, format = self._fields[field_id]
        size = struct.calcsize(format)
        self._image[offset:offset + size] = struct.pack(format, field_value)


class ProcessorState(StateImage):
    def __init__(self, image):
        fields = {
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
            'memptr': (26, '<H'),

            'iff1': (28, 'B'),
            'iff2': (29, 'B'),
            'int_mode': (30, 'B'),
            'index_rp_kind': (31, 'B'),
        }
        super().__init__(fields, image)

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

    def get_sp(self):
        return self.get('sp')

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

    def get_index_rp_kind(self):
        n = self.get('index_rp_kind')
        return {0: 'hl', 1: 'ix', 2: 'iy'}[n]


class MachineState(StateImage):
    def __init__(self, image):
        fields = {
            'ticks_since_int': (32, '<L'),
            'fetches_to_stop': (36, '<L'),
            'suppressed_int':  (40, 'B'),
            'border_color':    (41, 'B'),
        }
        super().__init__(fields, image)

    def is_suppressed_int(self):
        return bool(self.get('suppressed_int'))

    def suppress_int(self, suppress=True):
        self.set('suppressed_int', int(suppress))

    def set_fetches_limit(self, fetches_to_stop):
        self.set('fetches_to_stop', fetches_to_stop)

    def set_ticks_since_int(self, ticks):
        self.set('ticks_since_int', ticks)

    def get_border_color(self):
        return self.get('border_color')

    def set_border_color(self, color):
        self.set('border_color', color)


class Spectrum48(Spectrum48Base):
    def __init__(self):
        self.machine_kind = 'ZX Spectrum 48K'
        self.state_image = self.get_state_image()
        self.processor_state = ProcessorState(self.state_image)
        self._machine_state = MachineState(self.state_image)
        self.memory = self.get_memory()

        # Install ROM.
        self.memory[0:0x4000] = zx.get_rom_image(self.machine_kind)

    def get_processor_state(self):
        return self.processor_state

    def get_machine_state(self):
        return self._machine_state

    def install_processor_snapshot(self, snapshot):
        assert snapshot['id'] == 'processor_snapshot'
        for id, field in snapshot.items():
            if id == 'id':
                continue  # Already checked above.
            self.processor_state.set(id, field)

    def install_snapshot(self, snapshot):
        assert snapshot['id'] == 'snapshot'  # TODO
        # TODO: Reset this machine before installing the snapshot.
        for field, value in snapshot.items():
            if field == 'id':
                pass  # Already checked above.
            elif field == 'machine_kind':
                assert value == 'ZX Spectrum 48K'  # TODO
            elif field == 'memory':
                for addr, block in value:
                    self.memory[addr:addr + len(block)] = block
            elif field == 'processor_snapshot':
                self.install_processor_snapshot(value)
            elif field == 'border_color':
                self._machine_state.set_border_color(value)
            else:
                raise zx.Error("Unknown snapshot field '%s'." % field)
