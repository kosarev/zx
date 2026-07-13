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

import typing

import numpy

import zx
from zx._ay import AY
from zx._ay import AYPlayer
from zx._ay import AYRegisterWrite
from zx._data import AYFrame
from zx._data import AYStream
from zx._data import AYWrite
from zx._device import Device
from zx._device import DeviceEvent
from zx._device import Dispatcher
from zx._device import NewSoundPulses
from zx._device import TimeAdvanced
from zx._emulator import Machine
from zx._sound import SoundDevice
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


def make_ay() -> tuple[AY, _Collector, Dispatcher]:
    ay = AY(active=True)
    collector = _Collector()
    devices = Dispatcher([ay, collector])

    # The first stamp only synchronises; no chunk yet.
    devices.notify(TimeAdvanced(at(0)))
    return ay, collector, devices


def write(devices: Dispatcher, reg: int, value: int, tick: int) -> None:
    devices.notify(AYRegisterWrite(reg, value, at(tick)))


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
    with zx.Emulator(machine=Machine(ay=AY(active=True)),
                     environment=[player, sound]) as app:
        app.run(until=player.get_end_time() +
                Time(RATE // 10, ticks_per_second=RATE))

    samples = numpy.concatenate(sound.samples)
    assert len(samples) >= 44100 // 10
    assert numpy.abs(samples).max() > 0.0
