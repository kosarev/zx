#!/usr/bin/env python3

import zx
import pytest


def test_basic() -> None:
    # Create a record.
    assert list(zx._data.DataRecord()) == []

    # Define and access some fields.
    rec = zx._data.DataRecord(a=5, b=7)
    assert (getattr(rec, 'a'), getattr(rec, 'b')) == (5, 7)
    assert list(rec) == [('a', 5), ('b', 7)]
    assert 'DataRecord' in rec.dumps()

    # Create a snapshot.
    assert list(zx._data.MachineSnapshot()) == []

    # Unified snapshots convert to themselves.
    uni = zx._data.UnifiedSnapshot()
    assert uni.to_unified_snapshot() is uni
