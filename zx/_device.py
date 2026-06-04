# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.

import typing
import enum
import numpy

from ._binary import Bytes
from ._data import SoundFile
from ._data import SoundPulses
from ._data import UnifiedPlayback
from ._data import UnifiedSnapshot


class DeviceEvent(object):
    pass


class MenuItemDescriptor(object):
    def __init__(self, label: str,
                 hotkey: None | str = None) -> None:
        self.label = label
        self.hotkey = hotkey


class GetMainMenuItems(DeviceEvent):
    pass


class MenuItemHit(DeviceEvent):
    def __init__(self, item: MenuItemDescriptor) -> None:
        self.item = item


class Destroy(DeviceEvent):
    pass


# Resets the emulated machine to its power-on state and notifies all
# devices to discard any accumulated transient state. Dispatched both
# on explicit user request and before loading a file, so that the
# loaded state is applied on top of a clean reset state.
class EmulatorReset(DeviceEvent):
    pass


class SetFrameDuration(DeviceEvent):
    def __init__(self, num_fetches: int) -> None:
        self.num_fetches = num_fetches


class InstallSnapshot(DeviceEvent):
    def __init__(self, snapshot: UnifiedSnapshot) -> None:
        self.snapshot = snapshot


class StartPlayback(DeviceEvent):
    def __init__(self, playback: UnifiedPlayback) -> None:
        self.playback = playback


class StopPlayback(DeviceEvent):
    pass


class EndOfFrame(DeviceEvent):
    def __init__(self, *,
                 port_writes: numpy.typing.NDArray[numpy.uint64]):
        self.port_writes = port_writes


class OutputFrame(DeviceEvent):
    def __init__(self, *,
                 pixels: Bytes,
                 fast_forward: bool = False):
        self.pixels = pixels
        self.fast_forward = fast_forward


class GetEmulationPauseState(DeviceEvent):
    pass


class GetEmulationTime(DeviceEvent):
    pass


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
    def __init__(self, addr: int, ticks_since_int: int = 0) -> None:
        self.addr = addr
        self.ticks_since_int = ticks_since_int


class RequestLoadFile(DeviceEvent):
    pass


class RequestSaveSnapshot(DeviceEvent):
    pass


class SaveSnapshot(DeviceEvent):
    def __init__(self, filename: str):
        self.filename = filename


class TapeStateUpdated(DeviceEvent):
    pass


class ToggleEmulationPause(DeviceEvent):
    pass


class ToggleFullscreen(DeviceEvent):
    pass


class ToggleTapePause(DeviceEvent):
    pass


class NewSoundFrame(DeviceEvent):
    def __init__(self, pulses: SoundPulses) -> None:
        self.pulses = pulses


class Device(object):
    def on_event(self, event: DeviceEvent, devices: 'Dispatcher',
                 result: typing.Any) -> typing.Any:
        return result


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
    def notify(self, event: DeviceEvent, *,
               result: typing.Any = None) -> typing.Any:
        for device in self:
            result = device.on_event(event, self, result)
        return result
