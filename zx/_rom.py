# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2019 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.


import importlib.resources
import os


def load_rom_image(filename: str) -> bytes:
    path = importlib.resources.files('zx').joinpath('roms', filename)
    return path.read_bytes()
