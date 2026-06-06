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
import zx._rzx
import zx._z80snapshot
from zx._error import Error
from zx._main import recover_playback


def test_iregp_mid_instruction() -> None:
    # Build a snapshot with PC pointing at an IX-prefixed instruction in RAM.
    mach = zx.Spectrum(headless=True)
    mach.write(0x8000, b'\xdd\x21\x00\x00')  # LD IX, 0x0000
    mach.pc = 0x8000
    snapshot = zx._z80snapshot.Z80Snapshot.from_snapshot(mach.to_snapshot())

    # One frame ending after just the 0xdd prefix byte, leaving the machine
    # mid-IX instruction at the frame boundary.
    rzx_image = zx._rzx.make_rzx([
        zx._rzx.RZXSnapshot(format=b'Z80\x00', snapshot=snapshot),
        zx._rzx.RZXInputRecording(
            first_tick=0,
            frames=[zx._rzx.RZXFrame(num_fetches=1, samples=b'')]),
    ])
    rzx = zx._rzx.RZXFile.decode('test.rzx', rzx_image)

    with pytest.raises(Error) as exc_info:
        recover_playback(rzx)
    assert exc_info.value.id == 'iregp_mid_instruction'
