# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.


class EmulatorException(Exception):
    """Base class for exceptions raised by the emulator."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class EmulationExit(EmulatorException):
    """Raised to signal that emulation has stopped."""

    def __init__(self) -> None:
        super().__init__('Emulation stopped.')
