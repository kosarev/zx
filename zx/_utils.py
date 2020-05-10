# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2019 Ivan Kosarev.
#   ivan@kosarev.info
#
#   Published under the MIT license.


MASK16 = 0xffff


def div_ceil(a, b):
    return (a + b - 1) // b


def make16(hi, lo):
    return ((hi << 8) | lo) & MASK16


def _split16(nn):
    lo = nn & 0xff
    hi = (nn >> 8) & 0xff
    return lo, hi
