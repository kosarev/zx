#!/usr/bin/env python3

# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.

from __future__ import annotations

import math
import typing

import numpy

import zx
from zx._ay8910 import AY8910
from zx._ay8910 import AY8910RegisterWrite
from zx._ay8910 import AYPlayer
from zx._data import AYFrame
from zx._data import AYStream
from zx._data import AYWrite
from zx._device import CollectPortReads
from zx._device import Device
from zx._device import DeviceEvent
from zx._device import Dispatcher
from zx._device import NewPortReads
from zx._device import NewPortWrites
from zx._device import NewSoundPulses
from zx._device import RunQuantum
from zx._device import TimeAdvanced
from zx._machine import Machine
from zx._sound import SoundDevice
from zx._spectrum48 import Spectrum48MemoryMapping
from zx._time import Time

if typing.TYPE_CHECKING:
    from zx._data import SoundPulses

# The 128K CPU rate: 16 ticks per generator step.
RATE = 3546900
TICKS_PER_STEP = 16


class _Collector(Device):
    def __init__(self) -> None:
        self.chunks: list[SoundPulses] = []

    def on_event(self, event: DeviceEvent, devices: Dispatcher) -> None:
        if isinstance(event, NewSoundPulses):
            self.chunks.append(event.pulses)


def at(tick: int) -> Time:
    return Time(tick, ticks_per_second=RATE)


def make_ay() -> tuple[AY8910, _Collector, Dispatcher]:
    ay = AY8910()
    collector = _Collector()
    devices = Dispatcher([ay, collector])

    # The first stamp only synchronises; no chunk yet.
    devices.notify(TimeAdvanced(at(0)))
    return ay, collector, devices


def write(devices: Dispatcher, reg: int, value: int, tick: int) -> None:
    devices.notify(AY8910RegisterWrite(reg, value, at(tick)))


def test_tone_period() -> None:
    _, collector, devices = make_ay()

    # Tone A at period 5, full volume, tone-only mixing.
    write(devices, 0, 5, 0)
    write(devices, 7, 0b00111110, 0)
    write(devices, 8, 15, 0)

    devices.notify(TimeAdvanced(at(100 * TICKS_PER_STEP)))

    # One chunk per channel; combining them is the mixer's business.
    a, b, c = collector.chunks
    for chunk in a, b, c:
        assert chunk.rate == RATE
        assert chunk.num_ticks == 100 * TICKS_PER_STEP

    # Channel A flips every 5 steps, alternating between
    # -DAC(15) / 2 and its positive counterpart; B and C are flat.
    spacing = numpy.diff(a.ticks[1:])
    assert (spacing == 5 * TICKS_PER_STEP).all()

    levels = numpy.unique(a.levels)
    assert len(levels) == 2
    assert levels[0] == -levels[-1]
    assert abs(levels[-1] - 1 / 2) < 1e-9

    for chunk in b, c:
        assert len(chunk.ticks) == 1


def test_stream_on_the_48k_clock_keeps_the_chip_pitch() -> None:
    # The chip runs its own clock whatever the stream's timeline: a
    # stream stamped on the 48K clock renders on the same chip grid
    # as a 128K one, with the chunks at the exact common resolution
    # of the two timelines.
    rate = 3_500_000
    chunk_rate = math.lcm(rate, 1_773_450)

    ay = AY8910()
    collector = _Collector()
    devices = Dispatcher([ay, collector])
    devices.notify(TimeAdvanced(Time(0, ticks_per_second=rate)))

    for reg, value in (0, 5), (7, 0b00111110), (8, 15):
        devices.notify(AY8910RegisterWrite(
            reg, value, Time(0, ticks_per_second=rate)))

    span = rate // 100
    devices.notify(TimeAdvanced(Time(span, ticks_per_second=rate)))

    a = collector.chunks[0]
    assert a.rate == chunk_rate
    assert a.num_ticks == span * (chunk_rate // rate)

    # A generator step is 8 chip clocks on the chunk timeline; the
    # period-5 tone flips every 5 steps -- the 128K pitch, not a
    # step of 16 stamp ticks.
    ticks_per_step = 8 * (chunk_rate // 1_773_450)
    spacing = numpy.diff(a.ticks[1:])
    assert (spacing == 5 * ticks_per_step).all()


def test_sustained_level_has_no_transitions() -> None:
    _, collector, devices = make_ay()

    # Everything off: the chunks still define the level over the span.
    devices.notify(TimeAdvanced(at(1000)))

    assert len(collector.chunks) == 3
    for chunk in collector.chunks:
        assert chunk.num_ticks == 1000
        assert list(chunk.ticks) == [0]
        assert len(chunk.levels) == 1 and chunk.levels[0] == 0.0


def test_envelope_restart() -> None:
    _, collector, devices = make_ay()

    # Envelope mode on channel A with tone and noise mixing off (the
    # channel bit reads as 1), decay shape, period 1: one envelope
    # step per generator step, silence after 16 steps.
    write(devices, 7, 0b00111111, 0)
    write(devices, 8, 0x10, 0)
    write(devices, 11, 1, 0)
    write(devices, 13, 0, 0)

    devices.notify(TimeAdvanced(at(32 * TICKS_PER_STEP)))
    assert collector.chunks[-3].levels[-1] == 0.0

    # Rewriting the shape register with the same value restarts the
    # envelope: sound again.
    write(devices, 13, 0, 40 * TICKS_PER_STEP)
    devices.notify(TimeAdvanced(at(48 * TICKS_PER_STEP)))

    chunk = collector.chunks[-3]
    assert chunk.levels.max() > 0.0


def test_write_takes_effect_at_step_boundary() -> None:
    _, collector, devices = make_ay()

    # Constant full level: tone disabled reads as 1, fixed volume 15.
    write(devices, 7, 0b00111111, 0)

    # The volume write lands mid-step; its effect starts at the next
    # step boundary.
    write(devices, 8, 15, 3 * TICKS_PER_STEP + 7)
    devices.notify(TimeAdvanced(at(10 * TICKS_PER_STEP)))

    chunk = collector.chunks[0]
    assert list(chunk.ticks) == [0, 4 * TICKS_PER_STEP]
    assert chunk.levels[0] == 0.0
    assert abs(chunk.levels[1] - 1 / 2) < 1e-9


def port_writes(devices: Dispatcher, time_tick: int,
                writes: list[tuple[int, int, int]]) -> None:
    words = numpy.array([(tick << 32) | (value << 16) | addr
                         for tick, addr, value in writes],
                        dtype=numpy.uint64)
    devices.notify(NewPortWrites(at(time_tick), words))


def test_bus_interface() -> None:
    _, collector, devices = make_ay()

    # Tone A at period 5, full volume, tone-only mixing, driven
    # through the bus interface: writes to the 0xFFFD pattern latch
    # the register address, writes to the 0xBFFD pattern write the
    # addressed register — mirrors included, since the board's gates
    # only look at A15, A14 and A1. Writes to other devices' ports
    # are not the AY's business, and a latched value with the high
    # nibble set deselects the chip.
    port_writes(devices, 100, [
        (0, 0xfffd, 0),
        (0, 0xbffd, 5),
        (0, 0xc000, 7),
        (0, 0x8000, 0b00111110),
        (0, 0xfffd, 8),
        (0, 0xbffd, 15),
        (0, 0x00fe, 0x18),
        (0, 0xfffd, 0x10),
        (0, 0xbffd, 0xff)])

    devices.notify(TimeAdvanced(at(100 * TICKS_PER_STEP)))

    a, b, c = collector.chunks
    spacing = numpy.diff(a.ticks[1:])
    assert (spacing == 5 * TICKS_PER_STEP).all()

    levels = numpy.unique(a.levels)
    assert len(levels) == 2
    assert abs(levels[-1] - 1 / 2) < 1e-9

    for chunk in b, c:
        assert len(chunk.ticks) == 1


def test_bus_interface_stamp_rebase() -> None:
    # The per-write stamps are 32-bit and wrap; the event's closing
    # time rebases them onto the 64-bit axis.
    ay = AY8910()
    collector = _Collector()
    devices = Dispatcher([ay, collector])

    base = 1 << 32
    devices.notify(TimeAdvanced(at(base)))

    # The volume write lands mid-step, with its stamp wrapped; its
    # effect starts at the next step boundary.
    port_writes(devices, base + 10 * TICKS_PER_STEP, [
        (base & 0xffffffff, 0xfffd, 7),
        (base & 0xffffffff, 0xbffd, 0b00111111),
        ((base + 3 * TICKS_PER_STEP + 7) & 0xffffffff, 0xfffd, 8),
        ((base + 3 * TICKS_PER_STEP + 7) & 0xffffffff, 0xbffd, 15)])

    devices.notify(TimeAdvanced(at(base + 10 * TICKS_PER_STEP)))

    chunk = collector.chunks[0]
    assert list(chunk.ticks) == [0, 4 * TICKS_PER_STEP]
    assert chunk.levels[0] == 0.0
    assert abs(chunk.levels[1] - 1 / 2) < 1e-9


def test_stream_player() -> None:
    # A tone on channel A, with the pitch changed mid-way through
    # the second frame.
    stream = AYStream(
        ticks_per_second=RATE, ticks_per_frame=70908,
        frames=[
            AYFrame(frame=0, writes=[
                AYWrite(reg=7, value=0b00111110),
                AYWrite(reg=8, value=15),
                AYWrite(reg=0, value=100)]),
            AYFrame(frame=2, writes=[
                AYWrite(tick=100, reg=0, value=50)])])

    class _CapturingSound(SoundDevice):
        def __init__(self) -> None:
            self.samples: list[numpy.typing.NDArray[numpy.float32]] = []
            super().__init__()

        def _output(self,
                    samples: numpy.typing.NDArray[numpy.float32]) -> None:
            self.samples.append(samples)

    # The player is the session's runner; no core is present.
    player = AYPlayer(stream)
    sound = _CapturingSound()
    # The pad past the stream end covers the two spans that produce
    # no output -- the synthesiser renders nothing before its first
    # TimeAdvanced stamp, and the sound device consumes a published
    # chunk only on the following round -- each up to one quantum
    # long, plus the 0.1s of output the test expects.
    with zx.Emulator(machine=Machine(ay=AY8910()),
                     environment=[player, sound]) as app:
        app.run(until=player.get_end_time() +
                Time(3 * RATE // 10, ticks_per_second=RATE))

    samples = numpy.concatenate(sound.samples)
    assert len(samples) >= 44100 // 10
    assert numpy.abs(samples).max() > 0.0


# The given (tick, addr, value) port writes packed as the core's
# port-write words.
def _port_write_words(
        *writes: tuple[int, int, int]) -> (
        numpy.typing.NDArray[numpy.uint64]):
    return numpy.array([(tick << 32) | (value << 16) | addr
                        for tick, addr, value in writes],
                       dtype=numpy.uint64)


def test_ay_supplies_the_selected_register() -> None:
    # A read of the select/read port is answered with the selected
    # register's value at the floor, its unimplemented bits driven
    # low; a deselected chip, or an unimplemented register, drives
    # nothing.
    ay = AY8910()
    devices = Dispatcher([ay])

    devices.notify(NewPortWrites(at(100), _port_write_words(
        (10, 0xfffd, 1),         # select R1
        (20, 0xbffd, 0xff))))    # write 0xff to it
    devices.notify(TimeAdvanced(at(100)))

    collect = CollectPortReads(at(100), at(1000))
    devices.notify(collect)
    (series,) = collect.series
    assert (series.addr_mask, series.addr_value) == (0xc002, 0xc000)
    assert list(series.ticks) == [100]
    assert list(series.values) == [0x0f]
    assert series.end_tick == 101

    # A value with the high nibble set deselects the chip.
    devices.notify(NewPortWrites(at(200), _port_write_words(
        (150, 0xfffd, 0x10))))
    devices.notify(TimeAdvanced(at(200)))
    collect = CollectPortReads(at(200), at(1000))
    devices.notify(collect)
    assert collect.series == []

    # An unimplemented register drives nothing either.
    devices.notify(NewPortWrites(at(300), _port_write_words(
        (250, 0xfffd, 14))))
    devices.notify(TimeAdvanced(at(300)))
    collect = CollectPortReads(at(300), at(1000))
    devices.notify(collect)
    assert collect.series == []

    # A disabled AY supplies nothing at all.
    collect = CollectPortReads(at(300), at(1000))
    Dispatcher([AY8910(disabled=True)]).notify(collect)
    assert collect.series == []


def test_ay_register_read_on_a_core() -> None:
    # OUT, OUT, IN end to end: select a register, write it, read it
    # back within the same emulated stretch -- the read defers, the
    # published writes catch the register file up, and the next
    # collect answers with the value at the floor.
    core = zx.Core()
    ay = AY8910()
    devices = Dispatcher([core, ay])

    # An AY rig runs at the 128K clock, which the chip's clock
    # divides evenly.
    core.ticks_per_second = RATE

    core.write(Spectrum48MemoryMapping(), 0x8000,
               b'\x01\xfd\xff'   # LD BC, 0xfffd
               b'\x3e\x02'       # LD A, 2
               b'\xed\x79'       # OUT (C), A
               b'\x06\xbf'       # LD B, 0xbf
               b'\x3e\x3c'       # LD A, 0x3c
               b'\xed\x79'       # OUT (C), A
               b'\x06\xff'       # LD B, 0xff
               b'\xed\x78'       # IN A, (C)
               b'\x18\xfe')      # JR $
    core.pc = 0x8000

    floor = Time(0, ticks_per_second=RATE)
    deferred = None
    for _ in range(2):
        collect = CollectPortReads(floor, Time(100_000,
                                               ticks_per_second=RATE),
                                   deferred)
        devices.notify(collect)
        devices.notify(NewPortReads(floor, collect.series))

        run = RunQuantum()
        devices.notify(run)
        assert run.advanced_floor is not None
        floor = run.advanced_floor
        deferred = run.deferred_port_read_time
        devices.notify(TimeAdvanced(floor))

    assert core.a == 0x3c
