#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.


import importlib.resources


def load_rom_image(filename: str) -> bytes:
    path = importlib.resources.files('zx').joinpath('roms').joinpath(filename)
    return path.read_bytes()
