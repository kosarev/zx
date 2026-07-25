#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.

from __future__ import annotations

import enum
import typing

if typing.TYPE_CHECKING:
    import numpy

    from ._binary import Bytes
    from ._data import DeviceSnapshot
    from ._data import MachinePlayback
    from ._data import MachineSnapshot
    from ._data import PortReadSeries
    from ._data import SoundFile
    from ._data import SoundPulses
    from ._time import Time


class DeviceEvent:
    pass


# An emulation fact stamped with the emulated time it happened at.
class EmulationEvent(DeviceEvent):
    def __init__(self, time: Time) -> None:
        self.time = time


class MenuItemDescriptor:
    def __init__(self, label: str,
                 hotkey: str | None = None) -> None:
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


# The machine-level install, spoken by the environment and handled at
# the Emulator level, which splits it into per-device installs.
# Devices never handle this event.
class InstallSnapshot(DeviceEvent):
    def __init__(self, snapshot: MachineSnapshot) -> None:
        self.snapshot = snapshot


# The device-level install, always dispatched targeted: the addressed
# device assumes exactly the state the device snapshot describes --
# reset first, then apply what the snapshot mentions.
class InstallDeviceSnapshot(DeviceEvent):
    def __init__(self, snapshot: DeviceSnapshot) -> None:
        self.snapshot = snapshot


class StartPlayback(DeviceEvent):
    def __init__(self, playback: MachinePlayback) -> None:
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
        self.pixels: Bytes | None = None


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
    def __init__(self, time: Time,
                 writes: numpy.typing.NDArray[numpy.uint64]) -> None:
        super().__init__(time)
        self.writes = writes


# A quantum step: asks devices to supply port-read samples for the
# span from the floor up to the limit, assuming the quantum reaches
# the limit but without relying on it. A device that drives port
# input lines always handles this event, supplying an empty series
# when it can foretell nothing; the samples live for this quantum
# only and are collected anew each quantum.
#
# When the previous quantum ended on a deferred port read, its
# moment is carried here; a supplier judges by its own state
# whether that read is its business to answer.
class CollectPortReads(DeviceEvent):
    def __init__(self, floor: Time, limit: Time,
                 deferred_port_read_time: Time | None = None) -> None:
        self.floor = floor
        self.limit = limit
        self.deferred_port_read_time = deferred_port_read_time
        self.series: list[PortReadSeries] = []

    def supply(self, series: PortReadSeries) -> None:
        self.series.append(series)


# The port-read samples collected for the quantum starting at the
# stamped floor, published whole. The publication is the delivery:
# every device doing port I/O consumes it, the core first -- its
# C++-side samples are its copy of this stream.
class NewPortReads(EmulationEvent):
    def __init__(self, time: Time,
                 series: list[PortReadSeries]) -> None:
        super().__init__(time)
        self.series = series


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
        self.wake_in: float | None = None

    # Any device may hold; the earliest wake deadline wins. Holding
    # with no deadline relies on the waiting device's cap.
    def hold(self, wake_in: float | None = None) -> None:
        self.held = True
        if wake_in is not None:
            self.wake_within(wake_in)

    # A device that does not hold may still have a wallclock deadline
    # by which it wants the waiter woken (e.g. a presentation
    # refresh). This narrows the wake deadline without holding.
    def wake_within(self, wake_in: float) -> None:
        if self.wake_in is None or wake_in < self.wake_in:
            self.wake_in = wake_in


# Asks devices by what emulated time this quantum should stop. The
# emulated-time twin of GetHoldState: that one bounds how long the
# loop may sleep in wallclock time; this one bounds how far the
# machine runs before the next quantum. The earliest requested time
# wins; the Emulator requests its default span, so the limit is
# always defined and devices can only narrow it.
# The requested time is not a hard ceiling: a device stops at its
# first natural boundary at or after it — for the core, the next
# instruction boundary.
class GetQuantumTimeLimit(DeviceEvent):
    # The event is born with the default limit, floor + default_span,
    # so the limit is defined at all times.
    def __init__(self, floor: Time, default_span: Time) -> None:
        self.floor = floor
        self.stop_after_time = floor + default_span

    # Requests that the quantum stop right after the given time; the
    # earliest request wins. The floor is the first moment that has
    # not happened yet, so requests before it are meaningless.
    def stop_after(self, time: Time) -> None:
        assert self.floor <= time
        if time < self.stop_after_time:
            self.stop_after_time = time


class GetEmulationPauseState(DeviceEvent):
    def __init__(self) -> None:
        self.paused = False


class GetEmulationTime(DeviceEvent):
    def __init__(self) -> None:
        # The time all devices have advanced to, and the earliest
        # time none has reached yet -- where new facts, such as key
        # strokes, may land.
        self.floor: Time | None = None
        self.ceiling: Time | None = None


# TODO: Combine these into Get/SetState kind of events.
class GetTapePlayerTime(DeviceEvent):
    def __init__(self) -> None:
        self.time: Time | None = None


class IsTapePlayerPaused(DeviceEvent):
    def __init__(self) -> None:
        self.paused = False


class IsTapePlayerStopped(DeviceEvent):
    def __init__(self) -> None:
        self.stopped = False


class LoadTape(DeviceEvent):
    def __init__(self, file: SoundFile):
        self.file = file


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
                 wake_in: float | None = None,
                 stop_after: Time | None = None) -> None:
        self.held = held
        self.wake_in = wake_in

        # The quantum's time limit; devices advancing on this event
        # budget from their own positions in time.
        self.stop_after = stop_after

        # The devices' positions once the dispatch completes. A
        # position is the device's first uncommitted moment:
        # everything strictly before it has happened. The floor is
        # the earliest position, the ceiling the latest.
        self.advanced_floor: Time | None = None
        self.advanced_ceiling: Time | None = None

        # The moment of the deferred port read this quantum ended
        # on, if any; the next quantum's collect step carries it.
        self.deferred_port_read_time: Time | None = None

    # Devices advancing on this event report the position they have
    # advanced to.
    def advanced_to(self, time: Time) -> None:
        if self.advanced_floor is None or time < self.advanced_floor:
            self.advanced_floor = time
        if self.advanced_ceiling is None or self.advanced_ceiling < time:
            self.advanced_ceiling = time

    # A core whose quantum ended on a deferred port read reports the
    # read's moment. One core per machine so far, hence one report.
    def report_deferred_port_read(self, time: Time) -> None:
        assert self.deferred_port_read_time is None
        self.deferred_port_read_time = time


# Raised by a device to ask that the current quantum end now (e.g. the
# tape player when the tape runs out at a port read), so the run returns
# control at that exact tick. The machine stops the run in response.
class StopQuantum(DeviceEvent):
    pass


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
    # Maps snapshot types to the device types declaring them, so a
    # device can be created from any snapshot: Device.from_snapshot()
    # resolves the device type and delegates to its override.
    __device_types_by_snapshot_type: typing.ClassVar[
        dict[type[DeviceSnapshot], type[Device]]] = {}

    # The type of the device's snapshots; None where the device has
    # no state to describe.
    SNAPSHOT_TYPE: typing.ClassVar[type[DeviceSnapshot] | None] = None

    # Whether the device is excluded from the machine's operation. A
    # disabled device is indistinguishable from an absent one to the
    # emulated machine, but still receives the events that can
    # reconfigure it, such as InstallDeviceSnapshot. The class-level
    # default covers devices that do not call the initialiser.
    disabled: bool = False

    def __init__(self, *, disabled: bool = False) -> None:
        self.disabled = disabled

    def __init_subclass__(
            cls, *,
            snapshot_type: type[DeviceSnapshot] | None = None) -> None:
        if snapshot_type is not None:
            cls.SNAPSHOT_TYPE = snapshot_type

            types = Device.__device_types_by_snapshot_type
            assert snapshot_type not in types
            types[snapshot_type] = cls

    @classmethod
    def from_snapshot(cls, snapshot: DeviceSnapshot) -> Device:
        device_type = Device.__device_types_by_snapshot_type[type(snapshot)]
        assert device_type is not cls
        return device_type.from_snapshot(snapshot)

    # Captures the device's state. The default says the device holds
    # nothing beyond its canonical reset state, so there is nothing
    # to capture.
    def to_snapshot(self) -> DeviceSnapshot | None:
        return None

    def on_event(self, event: DeviceEvent, devices: Dispatcher) -> None:
        pass


# Passes events to the devices: to all of them, or, given a device
# id, to the addressed device only.
class Dispatcher:
    def __init__(self, devices: list[Device] | None = None, *,
                 devices_by_id: dict[str, Device] | None = None) -> None:
        if devices is None:
            devices = []

        self.__devices = list(devices)
        self.__devices_by_id = devices_by_id if devices_by_id else {}

    def notify(self, event: DeviceEvent, *,
               device: str | None = None) -> None:
        if device is not None:
            self.__devices_by_id[device].on_event(event, self)
            return

        for d in self.__devices:
            d.on_event(event, self)
