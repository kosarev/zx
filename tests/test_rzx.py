#!/usr/bin/env python3

import zx
import pytest


def test_basic() -> None:
    # Create a simple RZX.
    mach = zx.Emulator(speed_factor=None)
    mach.pc = 0x0001  # TODO: Null PC is not supported yet.
    snapshot = zx._z80snapshot.Z80SnapshotFormat().make_snapshot(mach)

    rzx_image = zx._rzx.make_rzx({
        'id': 'input_recording',
        'chunks': [
            {'id': 'info',
             'creator': b'<creator>',
             'creator_major_version': 1,
             'creator_minor_version': 0},
            {'id': 'snapshot',
             'image': snapshot},
            {'id': 'port_samples',
             'first_tick': 0,
             'frames': [(1, b''), (1, b'')]},
        ],
    })

    # Parse it back.
    format = zx._rzx.RZXFileFormat()
    assert format.NAME == 'RZX'
    rzx = format.parse('x.rzx', rzx_image)

    # Dump.
    assert 'RZXFile' in rzx.dumps()

    # Test finding the info block.
    player = zx._playback.PlaybackPlayer(mach, rzx)
    assert player.find_recording_info_chunk()['id'] == 'info'

    # Generate playback samples.
    assert 'END_OF_FRAME' in player.samples
