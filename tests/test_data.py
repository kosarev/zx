#!/usr/bin/env python3

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2025-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.


import zx


def test_basic() -> None:
    # Create a record.
    assert list(zx._data.DataRecord()) == []

    # Define and access some fields.
    rec = zx._data.DataRecord(a=5, b=7)
    # getattr (not rec.a) so mypy accepts access to the dynamic fields.
    assert (getattr(rec, 'a'), getattr(rec, 'b')) == (5, 7)  # noqa: B009
    assert list(rec) == [('a', 5), ('b', 7)]
    assert 'DataRecord' in rec.dumps()

    # Create a snapshot.
    assert list(zx._data.SnapshotFile()) == []

    # Machine snapshots convert to themselves.
    snapshot = zx._data.MachineSnapshot()
    assert snapshot.to_machine_snapshot() is snapshot
