# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.


import pathlib

from zx._data import Spectrum48
from zx._device import DestroyEmulator
from zx._device import Dispatcher
from zx._device import GetSettings
from zx._device import InitEmulator
from zx._device import SetSettingValue
from zx._settings import GlobalSettingsManager
from zx._sound import SoundDevice


def test_settings_round_trip(tmp_path: pathlib.Path) -> None:
    path = str(tmp_path / 'settings.json')

    # A changed setting is saved on shutdown...
    sound = SoundDevice(Spectrum48)
    dispatcher = Dispatcher([sound, GlobalSettingsManager(path)])
    dispatcher.notify(SetSettingValue('speed', 2.0))
    dispatcher.notify(DestroyEmulator())

    # ...and applied to a fresh device set on startup.
    sound = SoundDevice(Spectrum48)
    dispatcher = Dispatcher([sound, GlobalSettingsManager(path)])
    dispatcher.notify(InitEmulator())

    settings = GetSettings()
    dispatcher.notify(settings)
    speed = next(s for s in settings.settings if s.id == 'speed')
    assert speed.current == 2.0
