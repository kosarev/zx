#!/usr/bin/env python3

import zx
import pytest


def test_basic() -> None:
    # Create a Z80 snapshot.
    mach = zx.Spectrum(headless=True)
    mach.pc = 0x0001  # TODO: Null PC is not supported yet.
    HL = 0x1234
    mach.hl = HL
    format = zx._z80snapshot.Z80Snapshot
    assert format.FORMAT_NAME == 'Z80'
    image = format.from_snapshot(mach.to_snapshot()).encode()
    assert len(image) == 49248
    assert image[4:6] == HL.to_bytes(2, 'little')

    # Parse it back and check.
    snap = format.parse('x.z80', image)
    assert snap.hl == HL

    # Dump the parsed snapshot.
    assert 'Z80Snapshot' in snap.dumps()

    # Produce and dump unified snapshot.
    uni = snap.to_unified_snapshot()
    assert 'UnifiedSnapshot' in uni.dumps()
