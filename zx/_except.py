# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2020 Ivan Kosarev.
#   ivan@kosarev.info
#
#   Published under the MIT license.


class EmulatorException(Exception):
    def __init__(self, *args):
        super().__init__(*args)


class EmulationExit(EmulatorException):
    def __init__(self):
        super().__init__()
