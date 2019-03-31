# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2019 Ivan Kosarev.
#   ivan@kosarev.info
#
#   Published under the MIT license.


import os


def load_image(filename):
    current_dir = os.path.dirname(__file__)
    filename = os.path.join(current_dir, 'roms', filename)
    with open(filename, mode='rb') as f:
        return f.read()


def get_rom_image(machine_kind):
    rom_filenames = {'ZX Spectrum 48K': 'Spectrum48.rom'}
    return load_image(rom_filenames[machine_kind])
