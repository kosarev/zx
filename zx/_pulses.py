# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2025 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.

import numpy


# TODO: Should be DataRecord?
# TODO: Move to _data.py?
class Pulses(object):
    def __init__(self, rate: int,
                 levels: numpy.typing.NDArray[numpy.uint32],
                 ticks: numpy.typing.NDArray[numpy.uint32]) -> None:
        assert len(levels) == len(ticks)
        self.rate, self.levels, self.ticks = rate, levels, ticks
