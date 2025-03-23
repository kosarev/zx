#!/usr/bin/env python3

import zx
import pytest


def test_basic() -> None:
    # Create a SCR snapshot.
    mach = zx.Emulator(speed_factor=None)
    format = zx._scr._SCRSnapshot
    assert format.FORMAT_NAME == 'SCR'
    scr = format.make_snapshot(mach)

    # Dump.
    assert '_SCRSnapshot' in scr.dumps()

    # Produce and dump unified snapshot.
    uni = scr.get_unified_snapshot()
    assert 'UnifiedSnapshot' in uni.dumps()
