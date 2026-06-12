# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.


import numpy

from zx._data import Spectrum48
from zx._data import SoundPulses
from zx._data import SpectrumModel
from zx._device import Dispatcher
from zx._device import EmulatorReset
from zx._device import GetSettings
from zx._device import NewSoundPulses
from zx._device import QuantumRun
from zx._device import SetSettingValue
from zx._device import TimeAdvanced
from zx._sound import SoundDevice
from zx._sound import SPEED


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

    device.on_event(EmulatorReset(), dispatcher)

    # The first window only establishes the baseline tick position, so
    # nothing is produced yet.
    device.on_event(TimeAdvanced(0), dispatcher)
    device.on_event(QuantumRun(), dispatcher)
    assert device.output == []

    # A second window holding a constant level produces output samples,
    # all of that level — averaging a constant signal returns it.
    level = 100
    device.on_event(NewSoundPulses(_level_chunk(rate, level, span)),
                    dispatcher)
    device.on_event(TimeAdvanced(span), dispatcher)
    device.on_event(QuantumRun(), dispatcher)

    assert device.output
    samples = numpy.concatenate(device.output)
    assert len(samples) > 0
    assert numpy.allclose(samples, level)


def test_sound_device_speed_setting() -> None:
    dispatcher = Dispatcher()
    device = SoundDevice(Spectrum48)

    # The device advertises its speed setting, at the initial speed.
    settings = GetSettings()
    device.on_event(settings, dispatcher)
    speed = next(s for s in settings.settings if s.id == 'speed')
    assert speed.label == 'Speed'
    assert speed.current == SPEED
    assert 2.0 in speed.choices

    # Applying it through the generic event changes the reported value.
    device.on_event(SetSettingValue('speed', 2.0), dispatcher)
    settings = GetSettings()
    device.on_event(settings, dispatcher)
    speed = next(s for s in settings.settings if s.id == 'speed')
    assert speed.current == 2.0
