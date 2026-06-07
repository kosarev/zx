# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.


import zx
import pytest


def test_basic() -> None:
    # Create a simple RZX.
    mach = zx.Spectrum(headless=True)
    mach.pc = 0x0001  # TODO: Null PC is not supported yet.
    snapshot = zx._z80snapshot.Z80Snapshot.from_snapshot(mach.to_snapshot())
    snapshot_chunk = zx._rzx.RZXSnapshot(format=b'Z80\x00',
                                         snapshot=snapshot)

    rzx_image = zx._rzx.make_rzx([
        zx._rzx.RZXCreatorInfo(
            creator=zx._data.ByteData(b'<creator>'),
            creator_major_version=1,
            creator_minor_version=0),
        snapshot_chunk,
        zx._rzx.RZXInputRecording(
            first_tick=0,
            frames=[zx._rzx.RZXFrame(num_fetches=3, samples=b'\x42\xff\x00'),
                    zx._rzx.RZXFrame(num_fetches=1, samples=b'')]),
    ])

    # Parse it back.
    format = zx._rzx.RZXFile
    assert format.FORMAT_NAME == 'RZX'
    rzx = format.decode('x.rzx', rzx_image)

    # Dump.
    assert 'RZXFile' in rzx.dumps()

    # Verify creator info is carried into the unified playback.
    playback = rzx.to_unified_playback()
    assert playback.creator == '<creator>'
    assert not playback.is_spin_v05

    # Verify samples are consumed correctly from the first frame.
    player = zx._playback.PlaybackPlayer()
    dispatcher = zx._device.Dispatcher()
    start = zx._device.StartPlayback(playback)
    player.on_event(start, dispatcher)
    for expected in 0x42, 0xff, 0x00:
        read_port = zx._device.ReadPort(0xfe)
        player.on_event(read_port, dispatcher)
        assert read_port.value == expected
