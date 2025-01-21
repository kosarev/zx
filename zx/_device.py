# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2020 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.

import enum


class DeviceEvent(object):
    pass


class EndOfFrame(DeviceEvent):
    pass


class GetEmulationPauseState(DeviceEvent):
    pass


class GetEmulationTime(DeviceEvent):
    pass


class GetTapeLevel(DeviceEvent):
    def __init__(self, frame_tick):
        self.frame_tick = frame_tick


# TODO: Combine these into Get/SetState kind of events.
class GetTapePlayerTime(DeviceEvent):
    pass


class IsTapePlayerPaused(DeviceEvent):
    pass


class IsTapePlayerStopped(DeviceEvent):
    pass


class LoadTape(DeviceEvent):
    def __init__(self, file):
        self.file = file


class KeyStroke(DeviceEvent):
    def __init__(self, id, pressed):
        self.id = id
        self.pressed = pressed


class LoadFile(DeviceEvent):
    def __init__(self, filename):
        self.filename = filename


class PauseStateUpdated(DeviceEvent):
    pass


class PauseUnpauseTape(DeviceEvent):
    def __init__(self, pause):
        self.pause = pause


class QuantumRun(DeviceEvent):
    pass


class ReadPort(DeviceEvent):
    def __init__(self, addr):
        self.addr = addr


class SaveSnapshot(DeviceEvent):
    def __init__(self, filename):
        self.filename = filename


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
    def destroy(self):
        pass
