#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.


import pytest

import zx
from zx._error import Error


def test_basic() -> None:
    # Create a simple RZX with a snapshot of a standard machine.
    mach = zx.Core()
    mach.install_snapshot(zx._machines.Spectrum48Snapshot().core)
    mach.pc = 0x0001  # TODO: Null PC is not supported yet.
    snapshot = zx._z80.Z80Snapshot.from_snapshot(
        zx._data.MachineSnapshot(core=mach.to_snapshot()))
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

    # Verify creator info is carried into the machine playback.
    playback = rzx.to_machine_playback()
    assert playback.creator == '<creator>'
    assert not playback.is_spin_v05

    # Verify samples are consumed correctly from the first frame.
    player = zx._playback.PlaybackPlayer()
    dispatcher = zx._device.Dispatcher()
    start = zx._device.StartPlayback(playback)
    player.on_event(start, dispatcher)
    rate = zx._data.Spectrum48._TICKS_PER_FRAME * 50
    for expected in 0x42, 0xff, 0x00:
        read_port = zx._device.ReadPort(
            0xfe, zx._time.Time(0, ticks_per_second=rate))
        player.on_event(read_port, dispatcher)
        assert read_port.value == expected


def test_input_recording_without_snapshot() -> None:
    # An input recording before any snapshot would play against an
    # undefined machine state; no playable real-world file has one.
    rzx = zx._rzx.RZXFile(chunks=[
        zx._rzx.RZXInputRecording(first_tick=0, frames=[])])

    with pytest.raises(Error) as exc_info:
        rzx.to_machine_playback()
    assert exc_info.value.id == 'input_recording_without_snapshot'


def test_consecutive_input_recordings() -> None:
    # Several input recordings per snapshot would each rebase the tick
    # counter mid-segment; no playable real-world file has them.
    rzx = zx._rzx.RZXFile(chunks=[
        zx._rzx.RZXSnapshot(format=b'Z80\x00',
                            snapshot=zx._data.MachineSnapshot()),
        zx._rzx.RZXInputRecording(
            first_tick=0,
            frames=[zx._rzx.RZXFrame(num_fetches=1, samples=b'')]),
        zx._rzx.RZXInputRecording(first_tick=0, frames=[])])

    with pytest.raises(Error) as exc_info:
        rzx.to_machine_playback()
    assert exc_info.value.id == 'consecutive_input_recordings'
