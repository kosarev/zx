#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.


from zx._core import CoreSnapshot
from zx._core import Z80Snapshot
from zx._data import MachinePlayback
from zx._data import MachinePlaybackFrame
from zx._data import MachinePlaybackSegment
from zx._data import MachineSnapshot
from zx._device import CollectPortReads
from zx._device import Dispatcher
from zx._device import InstallSnapshot
from zx._device import StartPlayback
from zx._playback import PlaybackPlayer
from zx._playback import PlaybackRecorder
from zx._time import Time


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


def _collect() -> CollectPortReads:
    return CollectPortReads(Time(0, ticks_per_second=1),
                            Time(1, ticks_per_second=1))


def test_playback_devices_declare_all_ports() -> None:
    # The recorded samples are indexed by read order, so both
    # playing and recording need every read on the ReadPort path:
    # the empty all-addresses series declares that no read may
    # resolve from samples.
    dispatcher = Dispatcher()

    recorder = PlaybackRecorder()
    collect = _collect()
    recorder.on_event(collect, dispatcher)
    (series,) = collect.series
    assert (series.addr_mask, series.addr_value) == (0x0000, 0x0000)
    assert len(series.ticks) == 0

    collect = _collect()
    PlaybackRecorder(disabled=True).on_event(collect, dispatcher)
    assert collect.series == []

    # The player declares only while a playback is loaded.
    player = PlaybackPlayer()
    collect = _collect()
    player.on_event(collect, dispatcher)
    assert collect.series == []

    playback = MachinePlayback(segments=[MachinePlaybackSegment(
        snapshot=MachineSnapshot(),
        frames=[MachinePlaybackFrame(num_fetches=1,
                                     port_samples=b'\x42')])])
    player.on_event(StartPlayback(playback), dispatcher)
    collect = _collect()
    player.on_event(collect, dispatcher)
    (series,) = collect.series
    assert (series.addr_mask, series.addr_value) == (0x0000, 0x0000)
    assert len(series.ticks) == 0
