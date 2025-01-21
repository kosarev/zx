# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2021 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.


class EmulatorException(Exception):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


class EmulationExit(EmulatorException):
    def __init__(self):
        super().__init__('Emulation stopped.')
