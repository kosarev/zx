# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2020 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.

import typing
import enum
import numpy
from ._data import SoundFile
from ._pulses import Pulses


class DeviceEvent(object):
    pass


class Destroy(DeviceEvent):
    pass


class EndOfFrame(DeviceEvent):
    def __init__(self, *,
                 port_writes: numpy.typing.NDArray[numpy.uint64]):
        self.port_writes = port_writes


class OutputFrame(DeviceEvent):
    def __init__(self, *,
                 pixels: bytes,
                 fast_forward: bool = False):
        self.pixels = pixels
        self.fast_forward = fast_forward


class GetEmulationPauseState(DeviceEvent):
    pass


class GetEmulationTime(DeviceEvent):
    pass


class GetTapeLevel(DeviceEvent):
    def __init__(self, frame_tick: int) -> None:
        self.frame_tick = frame_tick


# TODO: Combine these into Get/SetState kind of events.
class GetTapePlayerTime(DeviceEvent):
    pass


class IsTapePlayerPaused(DeviceEvent):
    pass


class IsTapePlayerStopped(DeviceEvent):
    pass


class LoadTape(DeviceEvent):
    def __init__(self, file: SoundFile):
        self.file = file


class KeyStroke(DeviceEvent):
    def __init__(self, id: str, pressed: bool):
        self.id = id
        self.pressed = pressed


class LoadFile(DeviceEvent):
    def __init__(self, filename: str):
        self.filename = filename


class PauseStateUpdated(DeviceEvent):
    pass


class PauseUnpauseTape(DeviceEvent):
    def __init__(self, pause: bool):
        self.pause = pause


class QuantumRun(DeviceEvent):
    pass


class ReadPort(DeviceEvent):
    def __init__(self, addr: int):
        self.addr = addr


class SaveSnapshot(DeviceEvent):
    def __init__(self, filename: str):
        self.filename = filename


class TapeStateUpdated(DeviceEvent):
    pass


class ToggleEmulationPause(DeviceEvent):
    pass


class ToggleTapePause(DeviceEvent):
    pass


class NewSoundFrame(DeviceEvent):
    def __init__(self, source: str, pulses: Pulses) -> None:
        self.source, self.pulses = source, pulses


class Device(object):
    def on_event(self, event: DeviceEvent, devices: 'Dispatcher',
                 result: typing.Any) -> typing.Any:
        pass


class Dispatcher(object):
    __devices: typing.Iterable[Device]

    def __init__(self, devices: None | list[Device] = None) -> None:
        if devices is None:
            devices = []

        self.__devices = list(devices)

    def __iter__(self) -> typing.Iterator[Device]:
        yield from self.__devices

    # TODO: Since this now can return values, it needs a
    # different name.
    def notify(self, event: DeviceEvent,
               result: typing.Any = None) -> typing.Any:
        for device in self:
            result = device.on_event(event, self, result)
        return result
