#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.

import enum

import numpy

from ._binary import Bytes
from ._data import SoundFile
from ._data import SoundPulses
from ._data import UnifiedPlayback
from ._data import UnifiedSnapshot
from ._time import Time


class DeviceEvent:
    pass


# Emulation-related events are located in simulated time: facts
# carry their location, and consumers remember their own last seen
# positions and take wrap-aware differences of the free-running
# tick counter. UI-originated events are not located in simulated
# time and stay plain DeviceEvents.
class EmulationEvent(DeviceEvent):
    def __init__(self, tick_count: int) -> None:
        self.tick_count = tick_count


class MenuItemDescriptor:
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


# A value a setting can take.
SettingValue = float | int | str


# Where a setting belongs, which decides where it is persisted.
class SettingScope(enum.Enum):
    # A host/session preference (e.g. sound latency, refresh rate):
    # saved to the global preferences, never touched by loading
    # content such as snapshots or tapes.
    HOST = enum.auto()

    # Part of the loaded content (e.g. the model, key mappings): it
    # travels with snapshot and session files.
    CONTENT = enum.auto()


# Describes one setting a device owns: a stable id, the scope that
# decides where it is persisted, a human label, the discrete values it
# offers (for a clamped chooser in the UI), and its current value.
class SettingDescriptor:
    def __init__(self, id: str, scope: SettingScope, label: str,
                 choices: tuple[SettingValue, ...],
                 current: SettingValue) -> None:
        self.id = id
        self.scope = scope
        self.label = label
        self.choices = choices
        self.current = current


class GetSettings(DeviceEvent):
    def __init__(self) -> None:
        self.settings: list[SettingDescriptor] = []

    # Devices contribute their settings by adding them, so several
    # devices can populate the settings together.
    def add_settings(self, *settings: SettingDescriptor) -> None:
        self.settings.extend(settings)


# Applies a setting's value. Broadcast; the owning device self-selects
# by the setting id.
class SetSettingValue(DeviceEvent):
    def __init__(self, id: str, value: SettingValue) -> None:
        self.id = id
        self.value = value


# Instructs each device to do its local startup now that the set is
# assembled and live (dispatched on entering the emulator context),
# when it can finally reach its peers through the dispatcher — which
# __init__ cannot. The counterpart to DestroyEmulator.
class InitEmulator(DeviceEvent):
    pass


class DestroyEmulator(DeviceEvent):
    pass


# Resets the emulated machine to its power-on state and notifies all
# devices to discard any accumulated transient state. Dispatched both
# on explicit user request and before loading a file, so that the
# loaded state is applied on top of a clean reset state.
class ResetEmulator(DeviceEvent):
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


# Asks the machine for the current frame pixels. The core renders the
# screen up to the moment control returns, so the answer always
# reflects the present emulated state, mid-frame included. The screen
# pulls this at its own presentation rate, decoupled from the emulated
# frame rate.
class GetFramePixels(DeviceEvent):
    def __init__(self) -> None:
        self.pixels: None | Bytes = None


# Notified after every quantum that advanced emulation, carrying
# nothing but its stamp, so that time passes even when nothing else
# happened. Dispatched last: all facts about the elapsed span of
# time are published by the time its dispatch completes. Consumers
# may rely on that completion at the next dispatch — never on
# device order.
class TimeAdvanced(EmulationEvent):
    pass


# The writes collected by the stamped moment. Per-write stamps say
# when exactly each write happened and are strictly ordered within
# one event. Notified only when there are writes to report.
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

        # In how many seconds the earliest holding device expects the
        # answer to change, or a non-holding device wants the waiter
        # woken by (e.g. to meet a presentation deadline), or None
        # when only external input can change it. All answers are
        # given within one dispatch, so the durations are directly
        # comparable.
        self.wake_in: None | float = None

    # Any device may hold; the earliest wake deadline wins. Holding
    # with no deadline relies on the waiting device's cap.
    def hold(self, wake_in: None | float = None) -> None:
        self.held = True
        if wake_in is not None:
            self.wake_within(wake_in)

    # A device that does not hold may still have a wallclock deadline
    # by which it wants the waiter woken (e.g. a presentation
    # refresh). This narrows the wake deadline without holding.
    def wake_within(self, wake_in: float) -> None:
        if self.wake_in is None or wake_in < self.wake_in:
            self.wake_in = wake_in


# Asks devices after how many ticks this quantum should stop. The
# simulated-time twin of GetHoldState: where that bounds how long the
# loop may sleep in wallclock time, this bounds how far the machine
# runs in simulated time before the next quantum. The smallest
# declared value wins; with none declared the quantum runs to the
# frame end as usual.
# This is not a hard ceiling: the run loop only checks between
# instructions, so the quantum stops at the first instruction
# boundary at or after the requested point and may overshoot it by a
# whole instruction (we have no sub-instruction execution).
class GetQuantumTickLimit(DeviceEvent):
    def __init__(self) -> None:
        self.stop_after_ticks: None | int = None

    # A device requests that the quantum stop once it has advanced
    # the given number of ticks; the smallest such request wins.
    def stop_after(self, ticks: int) -> None:
        if self.stop_after_ticks is None or ticks < self.stop_after_ticks:
            self.stop_after_ticks = ticks


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


# Broadcast at the start of every loop iteration: the signal that a
# quantum is to be attempted now. It carries the hold state evaluated
# by the machine, so devices never re-query it -- when held, emulation
# does not advance this quantum (a held quantum is still a quantum),
# and a device that waits may sleep up to wake_in seconds (capped, and
# cut short by input).
class RunQuantum(DeviceEvent):
    def __init__(self, *, held: bool = False,
                 wake_in: None | float = None) -> None:
        self.held = held
        self.wake_in = wake_in


# Raised by a device to ask that the current quantum end now (e.g. the
# tape player when the tape runs out at a port read), so the run returns
# control at that exact tick. The machine stops the run in response.
class StopQuantum(DeviceEvent):
    pass


class ReadPort(EmulationEvent):
    def __init__(self, addr: int, tick_count: int = 0) -> None:
        super().__init__(tick_count)
        self.addr = addr

        # All input lines are pulled high unless a device drives
        # them low. None means a device cannot tell its input yet;
        # the input instruction is then aborted to be retried later.
        self.value: int | None = 0xff

    # Devices contribute their samples by ANDing them in, so several
    # devices can drive the same lines without overriding each other.
    # A deferred read stays deferred: the samples do not matter, as
    # the aborted instruction is to re-pose the read anyway.
    def supply(self, sample: int) -> None:
        if self.value is not None:
            self.value &= sample


class RequestLoadFile(DeviceEvent):
    pass


class SetBreakpoint(DeviceEvent):
    def __init__(self, addr: int) -> None:
        self.addr = addr


class SetFastForward(DeviceEvent):
    def __init__(self, active: bool) -> None:
        self.active = active


# How fast emulated time runs relative to wallclock. Only the sound
# path acts on it (as the resampler ratio); the rest of the machine is
# unaware of speed.
class SetEmulationSpeed(DeviceEvent):
    def __init__(self, speed: float) -> None:
        self.speed = speed


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


# A chunk of an emitter's continuous pulse stream, covering the
# span of time elapsed by the TimeAdvanced notification being
# dispatched.
class NewSoundPulses(DeviceEvent):
    def __init__(self, pulses: SoundPulses) -> None:
        self.pulses = pulses


class Device:
    def on_event(self, event: DeviceEvent, devices: 'Dispatcher') -> None:
        pass


# Broadcasts events to the devices.
class Dispatcher:
    def __init__(self, devices: None | list[Device] = None) -> None:
        if devices is None:
            devices = []

        self.__devices = list(devices)

    def notify(self, event: DeviceEvent) -> None:
        for device in self.__devices:
            device.on_event(event, self)
