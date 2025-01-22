#!/usr/bin/env python3

import zx
import pytest


def test_basic():
    # Create a SCR snapshot.
    mach = zx.Emulator()
    scr = zx._scr.SCRFileFormat().make_snapshot(mach)

    # Dump.
    assert 'zx._scr._SCRSnapshot' in scr.dump()

    # Produce and dump unified snapshot.
    uni = scr.get_unified_snapshot()
    assert 'zx._data.UnifiedSnapshot' in uni.dump()
