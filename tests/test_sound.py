# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.


import numpy

from zx._data import SoundPulses
from zx._data import Spectrum48
from zx._data import SpectrumModel
from zx._device import Dispatcher
from zx._device import GetSettings
from zx._device import NewSoundPulses
from zx._device import ResetEmulator
from zx._device import RunQuantum
from zx._device import SetSettingValue
from zx._device import SettingDescriptor
from zx._device import SettingScope
from zx._device import TimeAdvanced
from zx._sound import SoundDevice


# A sound device that captures the produced samples instead of playing
# them, so a test — or an API consumer — can read what the base
# SoundDevice generates without any audio hardware.
class _RecordingSound(SoundDevice):
    def __init__(self, model: type[SpectrumModel]) -> None:
        super().__init__(model)
        self.output: list[numpy.typing.NDArray[numpy.float32]] = []

    def _output(self, samples: numpy.typing.NDArray[numpy.float32]) -> None:
        self.output.append(samples)


# A chunk holding a single level over its whole span.
def _level_chunk(rate: int, level: int, num_ticks: int) -> SoundPulses:
    levels = numpy.array([level], dtype=numpy.uint32)
    ticks = numpy.array([0], dtype=numpy.uint32)
    return SoundPulses(rate, levels, ticks, num_ticks=num_ticks)


def test_sound_device_produces_samples() -> None:
    dispatcher = Dispatcher()
    device = _RecordingSound(Spectrum48)

    rate = Spectrum48._TICKS_PER_FRAME * 50
    span = Spectrum48._TICKS_PER_FRAME  # One frame's worth of ticks.

    device.on_event(ResetEmulator(), dispatcher)

    # The first window only establishes the baseline tick position, so
    # nothing is produced yet.
    device.on_event(TimeAdvanced(0), dispatcher)
    device.on_event(RunQuantum(), dispatcher)
    assert device.output == []

    # A second window holding a constant level produces output samples,
    # all of that level — averaging a constant signal returns it.
    level = 100
    device.on_event(NewSoundPulses(_level_chunk(rate, level, span)),
                    dispatcher)
    device.on_event(TimeAdvanced(span), dispatcher)
    device.on_event(RunQuantum(), dispatcher)

    assert device.output
    samples = numpy.concatenate(device.output)
    assert len(samples) > 0
    assert numpy.allclose(samples, level)


def test_sound_device_settings() -> None:
    dispatcher = Dispatcher()
    device = SoundDevice(Spectrum48)

    def report() -> dict[str, SettingDescriptor]:
        event = GetSettings()
        device.on_event(event, dispatcher)
        return {s.id: s for s in event.settings}

    # The device advertises at least one setting.
    settings = report()
    assert settings

    # Each setting starts at one of its choices and, applied through
    # the generic event to a different choice, reports the new value.
    for id, descriptor in settings.items():
        assert isinstance(descriptor.scope, SettingScope)
        assert descriptor.current in descriptor.choices
        if len(descriptor.choices) < 2:
            continue
        target = next(c for c in descriptor.choices
                      if c != descriptor.current)
        device.on_event(SetSettingValue(id, target), dispatcher)
        assert report()[id].current == target
