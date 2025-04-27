# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2019 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.


from ._except import EmulationExit
from ._except import EmulatorException
from ._main import main
from ._spectrum import Spectrum

__version__ = '0.11.0'

__all__ = ['Spectrum', 'main']
