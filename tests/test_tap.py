#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.


import zx
from zx._device import CollectPortReads
from zx._device import Dispatcher
from zx._device import GetQuantumTimeLimit
from zx._device import IsTapePlayerStopped
from zx._device import LoadTape
from zx._device import PauseUnpauseTape
from zx._device import TimeAdvanced
from zx._spectrum48 import Spectrum48MemoryMapping
from zx._tape import TapePlayer
from zx._time import Time


def test_basic() -> None:
    # Create a TAP file object.
    zx._tap.TAPFile(blocks=[b'abc', b'def'])

    # Parse a TAP file.
    data = b'123'
    block = len(data).to_bytes(2, 'little') + data
    format = zx._tap.TAPFile
    assert format.FORMAT_NAME == 'TAP'
    tap = format.decode('file.tap', block)

    # Generate pulses.
    tuple(tap.get_pulses())

    # Dump.
    assert 'TAPFile' in tap.dumps()


def test_tape_plays_to_the_end() -> None:
    # The tape commits its end as the floor passes it: the last
    # pulse is fetched, the tape reports itself stopped, and it
    # supplies nothing thereafter.
    tape = TapePlayer()
    devices = Dispatcher([tape])

    data = b'123'
    block = len(data).to_bytes(2, 'little') + data
    tape.on_event(LoadTape(zx._tap.TAPFile.decode('file.tap', block)),
                  devices)
    tape.on_event(PauseUnpauseTape(False), devices)

    stopped = IsTapePlayerStopped()
    tape.on_event(stopped, devices)
    assert not stopped.stopped

    # A floor far past the whole recording commits the end.
    tape.on_event(
        TimeAdvanced(Time(10 ** 9, ticks_per_second=3_500_000)),
        devices)

    stopped = IsTapePlayerStopped()
    tape.on_event(stopped, devices)
    assert stopped.stopped

    # An ended tape supplies nothing.
    collect = CollectPortReads(
        Time(10 ** 9, ticks_per_second=3_500_000),
        Time(10 ** 9 + 1000, ticks_per_second=3_500_000))
    tape.on_event(collect, devices)
    assert collect.series == []


# The tape's own resolution.
TAPE_RESOLUTION = 3_500_000


def _make_test_tape() -> zx._tap.TAPFile:
    data = b'123'
    block = len(data).to_bytes(2, 'little') + data
    return zx._tap.TAPFile.decode('file.tap', block)


def _collect_tape(tape: TapePlayer, limit_tick: int) -> CollectPortReads:
    event = CollectPortReads(
        Time(0, ticks_per_second=TAPE_RESOLUTION),
        Time(limit_tick, ticks_per_second=TAPE_RESOLUTION))
    tape.on_event(event, Dispatcher())
    return event


def test_tape_supplies_its_signal() -> None:
    # A playing tape states its signal as samples on its own
    # timeline: the level from the floor, changing at the pulse
    # boundaries, covering through the limit. With no tape loaded
    # there is no signal to drive, so nothing is supplied.
    assert _collect_tape(TapePlayer(), 1000).series == []

    tap = _make_test_tape()
    tape = TapePlayer()
    tape.on_event(LoadTape(tap), Dispatcher())
    tape.on_event(PauseUnpauseTape(False), Dispatcher())

    limit_tick = 100_000
    (series,) = _collect_tape(tape, limit_tick).series
    assert (series.addr_mask, series.addr_value) == (0x0001, 0x0000)
    assert series.ticks_per_second == TAPE_RESOLUTION
    assert series.end_tick == limit_tick + 1

    expected_ticks = [0]
    expected_values = []
    boundary = 0
    for level, duration, _ in tap.get_pulses():
        if boundary >= limit_tick + 1:
            break
        if boundary > 0:
            expected_ticks.append(boundary)
        expected_values.append(0xff if level else 0xbf)
        boundary += duration

    assert list(series.ticks) == expected_ticks
    assert list(series.values) == expected_values


def test_tape_supply_does_not_consume() -> None:
    # Supplying peeks the pulses without consuming: the same span
    # re-states identically, and the tape does not stop.
    tape = TapePlayer()
    tape.on_event(LoadTape(_make_test_tape()), Dispatcher())
    tape.on_event(PauseUnpauseTape(False), Dispatcher())

    (series,) = _collect_tape(tape, 100_000).series
    (again,) = _collect_tape(tape, 100_000).series
    assert list(series.ticks) == list(again.ticks)
    assert list(series.values) == list(again.values)

    stopped = IsTapePlayerStopped()
    tape.on_event(stopped, Dispatcher())
    assert not stopped.stopped


def test_tape_supply_bounded_at_the_end() -> None:
    # With the limit past the recording, the coverage ends where
    # the tape does; the tape drives nothing past its last pulse.
    tap = _make_test_tape()
    tape = TapePlayer()
    tape.on_event(LoadTape(tap), Dispatcher())
    tape.on_event(PauseUnpauseTape(False), Dispatcher())

    total = sum(duration for _, duration, _ in tap.get_pulses())
    (series,) = _collect_tape(tape, 100_000_000).series
    assert series.end_tick == total


def test_paused_tape_holds_its_level() -> None:
    # A paused tape's signal is frozen: one sample, covering the
    # whole span.
    tape = TapePlayer()
    tape.on_event(LoadTape(_make_test_tape()), Dispatcher())

    (series,) = _collect_tape(tape, 1000).series
    assert list(series.ticks) == [0]
    assert list(series.values) == [0xbf]
    assert series.end_tick == 1001


def test_tape_bounds_the_quantum_at_its_end() -> None:
    # The tape asks the quantum to stop right at the end-of-tape
    # moment, so emulation never runs past it; with the end beyond
    # the limit already requested, or the tape paused, it asks
    # nothing.
    tap = _make_test_tape()
    tape = TapePlayer()
    tape.on_event(LoadTape(tap), Dispatcher())

    total = sum(duration for _, duration, _ in tap.get_pulses())
    floor = Time(0, ticks_per_second=TAPE_RESOLUTION)
    end = Time(total, ticks_per_second=TAPE_RESOLUTION)

    # Paused: no request.
    limit = GetQuantumTimeLimit(floor, Time(100, ticks_per_second=1))
    tape.on_event(limit, Dispatcher())
    assert not (limit.stop_after_time < end)

    tape.on_event(PauseUnpauseTape(False), Dispatcher())

    # The end within the default span: the quantum stops there.
    limit = GetQuantumTimeLimit(floor, Time(100, ticks_per_second=1))
    tape.on_event(limit, Dispatcher())
    assert not (limit.stop_after_time < end)
    assert not (end < limit.stop_after_time)

    # The end beyond the span: nothing requested.
    span = Time(1000, ticks_per_second=TAPE_RESOLUTION)
    limit = GetQuantumTimeLimit(floor, span)
    tape.on_event(limit, Dispatcher())
    assert not (limit.stop_after_time < span)
    assert not (span < limit.stop_after_time)


def test_tape_read_from_samples() -> None:
    # In the Emulator loop, a read of the EAR port resolves from
    # the supplied samples on the C++ side. Port 0xfffe selects no
    # keyboard row, so the tape is the read's only driver.
    tap = _make_test_tape()
    first_level = next(iter(tap.get_pulses()))[0]

    with zx.Emulator(headless=True) as app:
        core = app.machine.devices['core']
        assert isinstance(core, zx.Core)
        core.write(Spectrum48MemoryMapping(), 0x8000,
                   b'\xdb\xfe'   # IN A, (0xfe)
                   b'\x18\xfe')  # JR $
        core.pc = 0x8000
        core.a = 0xff

        app.notify(LoadTape(tap))
        app.notify(PauseUnpauseTape(False))

        app.run(until=Time(1000,
                           ticks_per_second=core.ticks_per_second))
        assert core.a == (0xff if first_level else 0xbf)
