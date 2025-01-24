#!/usr/bin/env python3

import zx
import pytest


def test_basic():
    # Create a SCR snapshot.
    mach = zx.Emulator(speed_factor=None)
    format = zx._scr.SCRFileFormat()
    assert format._NAME == 'SCR'
    scr = format.make_snapshot(mach)

    # Dump.
    assert 'zx._scr._SCRSnapshot' in scr.dump()

    # Produce and dump unified snapshot.
    uni = scr.get_unified_snapshot()
    assert 'zx._data.UnifiedSnapshot' in uni.dump()
