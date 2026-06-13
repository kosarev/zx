# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.


from ._emulator import Emulator
from ._except import EmulationExit
from ._except import EmulatorException
from ._main import main
from ._spectrum import Spectrum

__version__ = '0.13.15'

__all__ = [
    'EmulationExit',
    'Emulator',
    'EmulatorException',
    'Spectrum',
    'main',
]
