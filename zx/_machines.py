#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.

"""Machine definitions as values.

A model is a stock snapshot installed like any other. Devices default
to inactive, so a stock snapshot explicitly activates its machine's
members. Converters compose their output over the stock snapshot of
the machine their format declares.

Each machine's types live in its own module (_spectrum48, _spectrum128)
as a capsule of that machine's knowledge; this module holds what they
share.
"""

import importlib.resources


def _load_rom_image(filename: str) -> bytes:
    path = importlib.resources.files('zx').joinpath('roms').joinpath(filename)
    return path.read_bytes()
