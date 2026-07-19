#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.


from zx._core import CoreSnapshot
from zx._core import Z80Snapshot
from zx._data import MachineSnapshot
from zx._device import Dispatcher
from zx._device import InstallSnapshot
from zx._playback import PlaybackRecorder


def test_playback_recorder() -> None:
    dispatcher = Dispatcher()
    snapshot1 = MachineSnapshot(core=CoreSnapshot(z80=Z80Snapshot(pc=0x8000)))
    snapshot2 = MachineSnapshot(core=CoreSnapshot(z80=Z80Snapshot(pc=0x9000)))

    # A disabled recorder ignores events.
    recorder = PlaybackRecorder(disabled=True)
    recorder.on_event(InstallSnapshot(snapshot1), dispatcher)
    assert recorder.make_playback().segments == []

    # The recorder starts a new segment per installed snapshot, in
    # order.
    recorder = PlaybackRecorder()
    recorder.on_event(InstallSnapshot(snapshot1), dispatcher)
    recorder.on_event(InstallSnapshot(snapshot2), dispatcher)

    playback = recorder.make_playback()
    assert [seg.snapshot for seg in playback.segments] == [
        snapshot1, snapshot2]
    assert all(seg.frames == [] for seg in playback.segments)

    # The recorded playback carries no creator identity, so it cannot
    # be re-detected as a quirky recording.
    assert not playback.is_spin_v05
