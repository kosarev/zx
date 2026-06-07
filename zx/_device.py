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
                 port_reads: Bytes) -> None:
        self.pixels = pixels
        self.port_reads = port_reads


# The bare heartbeat: notified after every quantum that advanced
# emulation, so that time passes even in silence. Dispatched last,
# as the finality point: all facts for the window it closes are
# published by the time its dispatch completes. Consumers may rely
# on that completion at the next dispatch — never on device order.
class TimeAdvanced(EmulationEvent):
    pass


# The tick_count stamp closes the collection window: these are the
# writes collected by that moment. Per-write stamps locate the
# writes within the window and are strictly ordered within one
# event. Notified only when there are writes to report.
class NewPortWrites(EmulationEvent):
    def __init__(self, tick_count: int,
                 writes: numpy.typing.NDArray[numpy.uint64]) -> None:
        super().__init__(tick_count)
        self.writes = writes


# Asks whether emulation must not advance this quantum, and for how
# long the answer is expected to stand.
class GetHoldState(DeviceEvent):
    def __init__(self) -> None:
        self.held = False

        # In how many seconds the earliest holder would like control
        # back, or None when only external input can change the
        # answer. All answers are given within one dispatch, so the
        # durations are directly comparable.
        self.wake_in: None | float = None

    # Any holder holds; the earliest wake deadline wins. A holder
    # with no deadline relies on the waiter's cap.
    def hold(self, wake_in: None | float = None) -> None:
        self.held = True
        if wake_in is not None:
            if self.wake_in is None or wake_in < self.wake_in:
                self.wake_in = wake_in


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


# Notified at the start of every loop iteration. Carries the hold
# state evaluated by the machine, so devices never re-query it: when
# held, emulation does not advance this quantum, and the waiter may
# sleep up to wake_in seconds (capped, and cut short by input).
class QuantumRun(DeviceEvent):
    def __init__(self, *, held: bool = False,
                 wake_in: None | float = None) -> None:
        self.held = held
        self.wake_in = wake_in


class ReadPort(EmulationEvent):
    def __init__(self, addr: int, tick_count: int = 0) -> None:
        super().__init__(tick_count)
        self.addr = addr

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


# A chunk of an emitter's continuous pulse stream, published for
# the window being closed by the current heartbeat dispatch.
class NewSoundPulses(DeviceEvent):
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
