#!/usr/bin/env python3

import zx
import pytest


def test_basic():
    # Create a record.
    assert list(zx._data.DataRecord()) == []

    # Define and access some fields.
    rec = zx._data.DataRecord(a=5, b=7)
    assert (rec.a, rec.b) == (5, 7)
    assert list(rec) == [('a', 5), ('b', 7)]
    assert 'zx._data.DataRecord' in rec.dump()

    # Create a file object.
    format = zx._data.FileFormat
    assert list(zx._data.File(format, x=9)) == [('x', 9)]

    # Create a snapshot.
    assert list(zx._data.MachineSnapshot(format)) == []
