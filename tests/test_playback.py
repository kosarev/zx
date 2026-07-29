#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.


import pytest

from zx._core import CoreSnapshot
from zx._core import Z80Snapshot
from zx._data import MachinePlayback
from zx._data import MachinePlaybackFrame
from zx._data import MachinePlaybackSegment
from zx._data import MachineSnapshot
from zx._device import CollectPortReads
from zx._device import Dispatcher
from zx._device import InstallSnapshot
from zx._device import NewPortReads
from zx._device import RunQuantum
from zx._device import StartPlayback
from zx._error import Error
from zx._playback import PlaybackPlayer
from zx._playback import PlaybackRecorder
from zx._spectrum48 import Spectrum48Core
from zx._spectrum48 import Spectrum48MemoryMapping
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


def test_playback_player_supplies_empty_series() -> None:
    # With no read deferred, the empty all-addresses series makes
    # every read unresolvable from samples, so it defers first; the
    # recorder supplies nothing at all -- it records amendments,
    # and the executed reads are the core's own stream to report.
    dispatcher = Dispatcher()

    collect = _collect()
    PlaybackRecorder().on_event(collect, dispatcher)
    assert collect.series == []

    # The player supplies only while a playback is loaded.
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


def test_playback_reads_defer_and_consume_in_order() -> None:
    # The player deals the recorded samples one per deferred read:
    # a read defers, the following collect supplies the next sample
    # at the read's moment, and the retry consumes it. IN A, (0xfe);
    # LD C, A; IN A, (0xfe) picks up the two samples in order.
    core = Spectrum48Core()
    player = PlaybackPlayer()
    devices = Dispatcher([core, player])

    core.write(Spectrum48MemoryMapping(), 0x8000,
               b'\xdb\xfe'   # IN A, (0xfe)
               b'\x4f'       # LD C, A
               b'\xdb\xfe'   # IN A, (0xfe)
               b'\x18\xfe')  # JR $
    core.pc = 0x8000
    core.a = 0x12

    playback = MachinePlayback(segments=[MachinePlaybackSegment(
        snapshot=MachineSnapshot(),
        frames=[MachinePlaybackFrame(num_fetches=100_000,
                                     port_samples=b'\x55\x66')])])
    devices.notify(StartPlayback(playback))

    rate = core.ticks_per_second
    floor = Time(0, ticks_per_second=rate)
    deferred = None
    for _ in range(3):
        collect = CollectPortReads(floor,
                                   Time(1000, ticks_per_second=rate),
                                   deferred)
        devices.notify(collect)
        devices.notify(NewPortReads(floor, collect.series))

        run = RunQuantum()
        devices.notify(run)
        assert run.advanced_floor is not None
        floor = run.advanced_floor
        deferred = run.deferred_port_read_time

    assert core.bc & 0xff == 0x55
    assert core.a == 0x66


def test_playback_deal_covers_through_the_deferred_moment() -> None:
    # A laggard device may keep the floor behind the deferred
    # read's moment; the dealt series covers from the floor through
    # the moment, so the read still resolves.
    player = PlaybackPlayer()
    dispatcher = Dispatcher()
    playback = MachinePlayback(segments=[MachinePlaybackSegment(
        snapshot=MachineSnapshot(),
        frames=[MachinePlaybackFrame(num_fetches=100,
                                     port_samples=b'\x55')])])
    player.on_event(StartPlayback(playback), dispatcher)

    collect = CollectPortReads(Time(10, ticks_per_second=100),
                               Time(1000, ticks_per_second=100),
                               Time(25, ticks_per_second=100))
    player.on_event(collect, dispatcher)
    (series,) = collect.series
    assert list(series.ticks) == [10]
    assert list(series.values) == [0x55]
    assert series.end_tick == 26


def test_too_few_samples_detected_at_collect() -> None:
    # A deferred read with the samples exhausted is an error,
    # detected at the collect step. The first collect
    # deals the last sample; the second, at a later deferred
    # moment, confirms it consumed and finds nothing left.
    player = PlaybackPlayer()
    dispatcher = Dispatcher()
    playback = MachinePlayback(segments=[MachinePlaybackSegment(
        snapshot=MachineSnapshot(),
        frames=[MachinePlaybackFrame(num_fetches=100,
                                     port_samples=b'\x55')])])
    player.on_event(StartPlayback(playback), dispatcher)

    collect = CollectPortReads(Time(10, ticks_per_second=100),
                               Time(1000, ticks_per_second=100),
                               Time(10, ticks_per_second=100))
    player.on_event(collect, dispatcher)
    assert len(collect.series) == 1

    with pytest.raises(Error) as exc_info:
        player.on_event(
            CollectPortReads(Time(25, ticks_per_second=100),
                             Time(1000, ticks_per_second=100),
                             Time(25, ticks_per_second=100)),
            dispatcher)
    assert exc_info.value.id == 'too_few_input_samples'


def test_playback_still_raises_on_too_few_samples() -> None:
    # A read with no samples remaining is an error, raised at the
    # collect step carrying the deferred read's moment.
    core = Spectrum48Core()
    player = PlaybackPlayer()
    devices = Dispatcher([core, player])

    core.write(Spectrum48MemoryMapping(), 0x8000,
               b'\xdb\xfe'   # IN A, (0xfe)
               b'\x4f'       # LD C, A
               b'\xdb\xfe'   # IN A, (0xfe)
               b'\x18\xfe')  # JR $
    core.pc = 0x8000
    core.a = 0x12

    playback = MachinePlayback(segments=[MachinePlaybackSegment(
        snapshot=MachineSnapshot(),
        frames=[MachinePlaybackFrame(num_fetches=100_000,
                                     port_samples=b'\x55')])])
    devices.notify(StartPlayback(playback))

    rate = core.ticks_per_second
    floor = Time(0, ticks_per_second=rate)
    deferred = None
    with pytest.raises(Error) as exc_info:
        for _ in range(3):
            collect = CollectPortReads(floor,
                                       Time(1000, ticks_per_second=rate),
                                       deferred)
            devices.notify(collect)
            devices.notify(NewPortReads(floor, collect.series))

            run = RunQuantum()
            devices.notify(run)
            assert run.advanced_floor is not None
            floor = run.advanced_floor
            deferred = run.deferred_port_read_time
    assert exc_info.value.id == 'too_few_input_samples'
