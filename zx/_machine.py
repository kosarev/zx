# -*- coding: utf-8 -*-

import zx
from ._emulator import Spectrum48Base

class Spectrum48(Spectrum48Base):
    def __init__(self):
        self.machine_kind = 'ZX Spectrum 48K'

        # Install ROM.
        memory = self.get_memory()
        memory[0:0x4000] = zx.get_rom_image(self.machine_kind)
