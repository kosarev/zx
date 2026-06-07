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
from ._time import Time


class DeviceEvent(object):
    pass


# Emulation-related events are located in simulated time: facts
# carry their location, and consumers hold cursors and take
# wrap-aware deltas of the free-running tick counter. UI-originated
# events are not located in simulated time and stay plain
# DeviceEvents.
class EmulationEvent(DeviceEvent):
    def __init__(self, tick_count: int) -> None:
        self.tick_count = tick_count


class MenuItemDescriptor(object):
    def __init__(self, label: str,
                 hotkey: None | str = None) -> None:
        self.label = label
        self.hotkey = hotkey


class GetMainMenuItems(DeviceEvent):
    def __init__(self) -> None:
        self.items: list[MenuItemDescriptor] = []

    # Devices contribute their items by adding them, so several
    # devices can populate the menu together.
    def add_items(self, *items: MenuItemDescriptor) -> None:
        self.items.extend(items)


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


class BreakpointHit(DeviceEvent):
    pass


class FetchesLimitHit(DeviceEvent):
    pass


class SetFetchesLimit(DeviceEvent):
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
    pass


class OutputFrame(DeviceEvent):
    def __init__(self, *,
                 pixels: Bytes,
                 port_writes: numpy.typing.NDArray[numpy.uint64],
                 port_reads: Bytes) -> None:
        self.pixels = pixels
        self.port_writes = port_writes
        self.port_reads = port_reads


class GetEmulationPauseState(DeviceEvent):
    def __init__(self) -> None:
        self.paused = False


class GetEmulationTime(DeviceEvent):
    def __init__(self) -> None:
        self.time = Time()


# TODO: Combine these into Get/SetState kind of events.
class GetTapePlayerTime(DeviceEvent):
    def __init__(self) -> None:
        self.time = Time()


class IsTapePlayerPaused(DeviceEvent):
    def __init__(self) -> None:
        self.paused = False


class IsTapePlayerStopped(DeviceEvent):
    def __init__(self) -> None:
        self.stopped = False


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


class ReadPort(EmulationEvent):
    def __init__(self, addr: int, tick_count: int = 0,
                 ticks_since_int: int = 0) -> None:
        super().__init__(tick_count)
        self.addr = addr

        # TODO: Retire in favour of the free-running tick_count once
        # the tape player moves off the frame-relative timeline.
        self.ticks_since_int = ticks_since_int

        # All input lines are pulled high unless a device drives
        # them low.
        self.value = 0xff

    # Devices contribute their samples by ANDing them in, so several
    # devices can drive the same lines without overriding each other.
    def supply(self, sample: int) -> None:
        self.value &= sample


class RequestLoadFile(DeviceEvent):
    pass


class SetBreakpoint(DeviceEvent):
    def __init__(self, addr: int) -> None:
        self.addr = addr


class SetFastForward(DeviceEvent):
    def __init__(self, active: bool) -> None:
        self.active = active


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
    def on_event(self, event: DeviceEvent, devices: 'Dispatcher') -> None:
        pass


class Dispatcher(object):
    __devices: typing.Iterable[Device]

    def __init__(self, devices: None | list[Device] = None) -> None:
        if devices is None:
            devices = []

        self.__devices = list(devices)

    def __iter__(self) -> typing.Iterator[Device]:
        yield from self.__devices

    def notify(self, event: DeviceEvent) -> None:
        for device in self:
            device.on_event(event, self)
