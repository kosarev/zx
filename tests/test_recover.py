#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.


import pytest

import zx
from zx._core import CoreSnapshot
from zx._core import MemorySnapshot
from zx._core import Z80Snapshot
from zx._data import MachinePlayback
from zx._data import MachinePlaybackFrame
from zx._data import MachinePlaybackSegment
from zx._data import MachineSnapshot
from zx._data import MemoryBlock
from zx._error import Error
from zx._except import EmulationExit
from zx._main import recover_playback


def assert_plays_ok(playback: MachinePlayback) -> None:
    with zx.Emulator(headless=True) as machine:
        try:
            machine._load_input_recording(playback)
            machine.run()
        except EmulationExit:
            pass


def assert_play_fails(playback: MachinePlayback, error_id: str) -> None:
    with (pytest.raises(Error) as exc_info,
          zx.Emulator(headless=True) as machine):
        machine._load_input_recording(playback)
        machine.run()
    assert exc_info.value.id == error_id


def test_iregp_mid_instruction() -> None:
    # One frame ending after just the 0xdd prefix byte, leaving the machine
    # mid-IX instruction at the frame boundary.
    snapshot = MachineSnapshot(core=CoreSnapshot(
        active=True,
        z80=Z80Snapshot(pc=0x8000),
        memory=MemorySnapshot(blocks=[MemoryBlock(
            addr=0x8000,
            data=b'\xdd\x21\x00\x00')])))  # LD IX, 0x0000

    playback = MachinePlayback(
        segments=[MachinePlaybackSegment(
            snapshot=snapshot,
            frames=[MachinePlaybackFrame(
                num_fetches=1, port_samples=b'')])])

    assert_plays_ok(recover_playback(playback))


def test_spin_v05_trailing_in_sample() -> None:
    # SPIN v0.5 records num_fetches=1 (first IN's M1 cycle only), leaving
    # the second IN's sample unconsumed at the frame boundary.
    snapshot = MachineSnapshot(core=CoreSnapshot(
        active=True,
        z80=Z80Snapshot(pc=0x8000),
        memory=MemorySnapshot(blocks=[MemoryBlock(
            addr=0x8000,
            data=b'\xdb\xfe\xdb\xfe')])))  # IN A,(0xfe) x2

    playback = MachinePlayback(
        segments=[MachinePlaybackSegment(
            snapshot=snapshot,
            frames=[MachinePlaybackFrame(
                num_fetches=1, port_samples=b'\xff\xff')])],
        creator='SPIN 0.5',
        creator_major_version=0,
        creator_minor_version=5)

    assert_play_fails(playback, 'too_many_input_samples')

    assert_plays_ok(recover_playback(playback))


def test_spin_v05_bytes_saving_trap() -> None:
    # SPIN v0.5 in fast save mode calls the bytes-saving ROM procedure at
    # 0x04d4 but expects it to be skipped (returning to the caller).
    snapshot = MachineSnapshot(core=CoreSnapshot(
        active=True,
        z80=Z80Snapshot(pc=0x8000, sp=0xc000),
        memory=MemorySnapshot(blocks=[MemoryBlock(
            addr=0x8000,
            data=b'\xcd\xd4\x04')])))  # CALL 0x04d4

    playback = MachinePlayback(
        segments=[MachinePlaybackSegment(
            snapshot=snapshot,
            frames=[MachinePlaybackFrame(
                num_fetches=1, port_samples=b'')])],
        creator='SPIN 0.5',
        creator_major_version=0,
        creator_minor_version=5)

    assert_plays_ok(recover_playback(playback))
