#!/usr/bin/env python3

import zx
import pytest


def test_basic() -> None:
    # Create a SCR snapshot.
    mach = zx.Spectrum(headless=True)
    format = zx._scr._SCRSnapshot
    assert format.FORMAT_NAME == 'SCR'
    # TODO: scr = format.make_snapshot(mach)

    # Dump.
    # TODO: assert '_SCRSnapshot' in scr.dumps()

    # Produce and dump unified snapshot.
    # TODO: uni = scr.to_unified_snapshot()
    # TODO: assert 'UnifiedSnapshot' in uni.dumps()
