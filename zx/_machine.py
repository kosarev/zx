# -*- coding: utf-8 -*-

import zx
from ._emulator import Spectrum48Base

class Spectrum48(Spectrum48Base):
    def __init__(self):
        self.machine_kind = 'ZX Spectrum 48K'

        # Install ROM.
        self.memory = self.get_memory()
        self.memory[0:0x4000] = zx.get_rom_image(self.machine_kind)

    def install_snapshot(self, snapshot):
        assert snapshot['id'] == 'snapshot'
        for id, field in snapshot.items():
            if id == 'id':
                pass  # Already checked above.
            elif id == 'machine_kind':
                assert field == 'ZX Spectrum 48K'  # TODO
            elif id == 'memory':
                for addr, block in field:
                    self.memory[addr:addr + len(block)] = block
            elif id == 'processor_state':
                pass  # TODO
            elif id == 'border_color':
                pass  # TODO
            else:
                raise zx.Error("Unknown snapshot field '%s'." % id)
