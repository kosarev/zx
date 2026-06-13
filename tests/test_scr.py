#!/usr/bin/env python3

# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.


import zx


def test_basic() -> None:
    # Create a SCR snapshot.
    mach = zx.Spectrum()
    format = zx._scr._SCRSnapshot
    assert format.FORMAT_NAME == 'SCR'
    # TODO: scr = format.make_snapshot(mach)

    # Dump.
    # TODO: assert '_SCRSnapshot' in scr.dumps()

    # Produce and dump unified snapshot.
    # TODO: uni = scr.to_unified_snapshot()
    # TODO: assert 'UnifiedSnapshot' in uni.dumps()
