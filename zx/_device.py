# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2020 Ivan Kosarev.
#   ivan@kosarev.info
#
#   Published under the MIT license.

import enum


class DeviceEvent(object):
    pass


class PauseStateUpdated(DeviceEvent):
    pass


class QuantumRun(DeviceEvent):
    pass


class ScreenUpdated(DeviceEvent):
    def __init__(self, pixels):
        self.pixels = pixels


class TapeStateUpdated(DeviceEvent):
    pass


class ToggleEmulationPause(DeviceEvent):
    pass


class ToggleTapePause(DeviceEvent):
    pass


class Device(object):
    def __init__(self, xmachine):
        self.xmachine = xmachine
