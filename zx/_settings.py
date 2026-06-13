#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.


import json
import pathlib

from ._device import DestroyEmulator
from ._device import Device
from ._device import DeviceEvent
from ._device import Dispatcher
from ._device import GetSettings
from ._device import InitEmulator
from ._device import SetSettingValue
from ._device import SettingScope


# Persists host-scoped settings to a JSON file: applies them on startup
# (InitEmulator) and saves them on shutdown (DestroyEmulator). It owns
# no settings — the owning devices do; this only routes their values to
# and from the file. Attached only by the end-user tool layer, so an
# API- or test-built emulator stays hermetic.
class GlobalSettingsManager(Device):
    def __init__(self, filename: pathlib.Path) -> None:
        self.__filename = filename

    # A missing file is the normal first run (use the defaults); a
    # corrupt one is not silently ignored — json.load raises.
    def __load(self, dispatcher: Dispatcher) -> None:
        if not self.__filename.exists():
            return
        with self.__filename.open() as f:
            values = json.load(f)
        for id, value in values.items():
            dispatcher.notify(SetSettingValue(id, value))

    def __save(self, dispatcher: Dispatcher) -> None:
        settings = GetSettings()
        dispatcher.notify(settings)
        values = {s.id: s.current for s in settings.settings
                  if s.scope == SettingScope.HOST}
        with self.__filename.open('w') as f:
            json.dump(values, f, indent=2)

    def on_event(self, event: DeviceEvent,
                 dispatcher: Dispatcher) -> None:
        if isinstance(event, InitEmulator):
            self.__load(dispatcher)
        elif isinstance(event, DestroyEmulator):
            self.__save(dispatcher)
