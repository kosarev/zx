# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2019 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.


import typing


def div_ceil(a: int, b: int) -> int:
    return (a + b - 1) // b


def make16(hi: int, lo: int) -> int:
    return (hi << 8) + lo


def tupilize(x: typing.Any) -> tuple[typing.Any, ...]:
    if isinstance(x, (tuple, list)):
        return tuple(x)
    return x,
