#!/usr/bin/env python3

import zx
import pytest


def test_basic():
    # Create a Z80 snapshot.
    mach = zx.Emulator(speed_factor=None)
    mach.pc = 0x0001  # TODO: Null PC is not supported yet.
    HL = 0x1234
    mach.hl = HL
    format = zx._z80snapshot.Z80SnapshotFormat()
    image = format.make_snapshot(mach)
    assert len(image) == 49182
    assert image[4:6] == HL.to_bytes(2, 'little')

    # Parse it back and check.
    snap = format.parse('x.z80', image)
    assert snap.hl == HL

    # Dump the parsed snapshot.
    assert 'zx._z80snapshot.Z80Snapshot' in snap.dump()

    # Produce and dump unified snapshot.
    uni = snap.get_unified_snapshot()
    assert 'zx._data.UnifiedSnapshot' in uni.dump()
