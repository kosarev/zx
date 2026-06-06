# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.


import pytest
import zx
from zx._data import MemoryBlock
from zx._data import UnifiedPlayback
from zx._data import UnifiedPlaybackFrame
from zx._data import UnifiedPlaybackSegment
from zx._data import UnifiedSnapshot
from zx._error import Error
from zx._main import recover_playback


def test_iregp_mid_instruction() -> None:
    # One frame ending after just the 0xdd prefix byte, leaving the machine
    # mid-IX instruction at the frame boundary.
    snapshot = UnifiedSnapshot(
        pc=0x8000,
        memory_blocks=[MemoryBlock(
            addr=0x8000,
            data=b'\xdd\x21\x00\x00')])  # LD IX, 0x0000

    playback = UnifiedPlayback(
        segments=[UnifiedPlaybackSegment(
            snapshot=snapshot,
            frames=[UnifiedPlaybackFrame(
                num_fetches=1, port_samples=b'')])])

    recover_playback(playback)


def test_spin_v05_trailing_in_sample() -> None:
    # SPIN v0.5 records num_fetches=1 (first IN's M1 cycle only), leaving
    # the second IN's sample unconsumed at the frame boundary.
    snapshot = UnifiedSnapshot(
        pc=0x8000,
        memory_blocks=[MemoryBlock(
            addr=0x8000,
            data=b'\xdb\xfe\xdb\xfe')])  # IN A,(0xfe) x2

    playback = UnifiedPlayback(
        segments=[UnifiedPlaybackSegment(
            snapshot=snapshot,
            frames=[UnifiedPlaybackFrame(
                num_fetches=1, port_samples=b'\xff\xff')])],
        creator='SPIN 0.5',
        creator_major_version=0,
        creator_minor_version=5)

    with pytest.raises(Error) as exc_info:
        recover_playback(playback)
    assert exc_info.value.id == 'spin_v05_trailing_in_sample'
