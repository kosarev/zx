#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.

from __future__ import annotations

import numpy

from zx._data import MachineSnapshot
from zx._data import SoundPulses
from zx._device import Dispatcher
from zx._device import InstallMachineSnapshot
from zx._device import NewSoundPulses
from zx._device import TimeAdvanced
from zx._main import _SilenceWatcher
from zx._time import Time


def _stamp(watcher: _SilenceWatcher, second: int) -> None:
    watcher.on_event(TimeAdvanced(Time(second, ticks_per_second=1)),
                     Dispatcher())


def _chunk(watcher: _SilenceWatcher, *levels: float) -> None:
    pulses = SoundPulses(
        1000, numpy.array(levels, dtype=numpy.float64),
        numpy.arange(len(levels), dtype=numpy.uint32) * 10,
        num_ticks=1000)
    watcher.on_event(NewSoundPulses(pulses), Dispatcher())


def test_silence_watcher() -> None:
    # Nothing sounding counts as silence from the first stamp on,
    # so a track that never sounds ends too.
    watcher = _SilenceWatcher()
    assert not watcher.is_silent_for(6)

    _stamp(watcher, 0)
    _stamp(watcher, 5)
    assert not watcher.is_silent_for(6)
    _stamp(watcher, 6)
    assert watcher.is_silent_for(6)

    # A chunk holding one level the whole span is not sound; a
    # transition is, and the silence then counts from the following
    # stamp.
    watcher = _SilenceWatcher()
    _stamp(watcher, 0)
    _chunk(watcher, 0.5)
    _chunk(watcher, 0.0, 1.0)
    _stamp(watcher, 4)
    _chunk(watcher, 0.5)
    _stamp(watcher, 9)
    assert not watcher.is_silent_for(6)
    _stamp(watcher, 10)
    assert watcher.is_silent_for(6)

    # Installing a snapshot restarts the watch: the next song
    # starts with a clean slate.
    watcher.on_event(InstallMachineSnapshot(MachineSnapshot()), Dispatcher())
    assert not watcher.is_silent_for(6)
    _stamp(watcher, 11)
    _stamp(watcher, 16)
    assert not watcher.is_silent_for(6)
    _stamp(watcher, 17)
    assert watcher.is_silent_for(6)
