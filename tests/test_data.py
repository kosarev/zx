#!/usr/bin/env python3

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2025-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.


import typing

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


def test_machine_lift() -> None:
    from zx._beeper import BeeperSnapshot
    from zx._keyboard import KeyboardSnapshot
    from zx._spectrum48 import Spectrum48CoreSnapshot
    from zx._spectrum48 import Spectrum48Snapshot

    core = zx.Core()
    core.install_snapshot(Spectrum48CoreSnapshot())

    # A saved default machine recognises as the stock 48K.
    machine = zx._data.MachineSnapshot(
        core=core.to_snapshot(),
        keyboard=KeyboardSnapshot(active=True),
        beeper=BeeperSnapshot(active=True))
    lifted = machine.lift()
    assert isinstance(lifted, Spectrum48Snapshot)
    assert isinstance(lifted.core, Spectrum48CoreSnapshot)

    # A composition that is no known machine stays plain, its
    # members still lifted.
    partial = zx._data.MachineSnapshot(core=core.to_snapshot())
    lifted_partial = partial.lift()
    assert type(lifted_partial) is zx._data.MachineSnapshot
    # getattr so mypy accepts access to the dynamic fields.
    assert isinstance(getattr(lifted_partial, 'core'),  # noqa: B009
                      Spectrum48CoreSnapshot)


# Record fields may only hold ints, strings, other records, and
# lists or tuples of those. Raw bytes and plain dicts do not
# serialise; they must be wrapped in record types such as ByteData.
def test_fields_are_serialisable_types() -> None:
    def all_record_types(
            cls: type) -> typing.Iterator[type]:
        yield cls
        for sub in cls.__subclasses__():
            yield from all_record_types(sub)

    def leaf_types(hint: object) -> typing.Iterator[object]:
        origin = typing.get_origin(hint)
        if origin is None:
            yield hint
            return
        yield origin
        for arg in typing.get_args(hint):
            yield from leaf_types(arg)

    for cls in all_record_types(zx._data.DataRecord):
        # The ByteData wrappers are the sanctioned holders of raw
        # bytes, serialising them themselves.
        if issubclass(cls, zx._data.ByteData):
            continue

        for name, hint in typing.get_type_hints(cls).items():
            if typing.get_origin(hint) is typing.ClassVar:
                continue
            for leaf in leaf_types(hint):
                assert leaf not in (bytes, bytearray, memoryview, dict), (
                    f'{cls.__name__}.{name} holds {leaf!r}')
