# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.


from zx._data import UnifiedSnapshot
from zx._device import Dispatcher
from zx._device import InstallSnapshot
from zx._playback import PlaybackRecorder


def test_playback_recorder() -> None:
    dispatcher = Dispatcher()
    snapshot1 = UnifiedSnapshot(pc=0x8000)
    snapshot2 = UnifiedSnapshot(pc=0x9000)

    # Inactive by default: events are ignored.
    recorder = PlaybackRecorder()
    recorder.on_event(InstallSnapshot(snapshot1), dispatcher, None)
    assert recorder.make_playback().segments == []

    # An active recorder starts a new segment per installed snapshot,
    # in order.
    recorder = PlaybackRecorder(active=True)
    recorder.on_event(InstallSnapshot(snapshot1), dispatcher, None)
    recorder.on_event(InstallSnapshot(snapshot2), dispatcher, None)

    playback = recorder.make_playback()
    assert [seg.snapshot for seg in playback.segments] == [
        snapshot1, snapshot2]
    assert all(seg.frames == [] for seg in playback.segments)

    # The recorded playback carries no creator identity, so it cannot
    # be re-detected as a quirky recording.
    assert not playback.is_spin_v05
