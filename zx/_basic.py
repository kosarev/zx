#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.

"""Driving a machine's ROM BASIC from code.

The shared scaffolding of the converters that run a private
headless machine through its ROM: boot to the BASIC prompt, type,
and capture the result.
"""

from __future__ import annotations

import typing

from ._device import BreakpointHit
from ._device import Device
from ._device import DeviceEvent
from ._device import Dispatcher
from ._device import IsTapePlayerStopped
from ._device import LoadTape
from ._device import TimeAdvanced
from ._except import EmulationExit
from ._spectrum48 import Spectrum48
from ._spectrum48 import Spectrum48CoreSnapshot
from ._spectrum48 import Spectrum48Snapshot
from ._time import Time

if typing.TYPE_CHECKING:
    from ._core import Core
    from ._emulator import Emulator

# The 48K boot settles at the BASIC prompt well within this many
# frames of 69,888 ticks.
_BOOT_FRAMES = 90
_TICKS_PER_FRAME = 69888


# Runs a freshly constructed 48K machine from power-up to the BASIC
# prompt.
def boot_to_prompt(app: Emulator) -> None:
    machine = app.machine
    assert isinstance(machine, Spectrum48)
    app.run(until=Time(_BOOT_FRAMES * _TICKS_PER_FRAME,
                       ticks_per_second=machine.core._ticks_per_second))


# Ends the run at a breakpoint, with PC still at the marked
# instruction: raising here happens before the core would step
# over it.
class StopAtBreakpoint(Device):
    def on_event(self, event: DeviceEvent, devices: Dispatcher) -> None:
        if isinstance(event, BreakpointHit):
            raise EmulationExit()


# Ends the run as soon as the tape player reports itself stopped,
# once per loaded tape, so runs after the end are free to continue.
# The tape bounds the quanta at the end-of-tape moment, so the run
# ends right there. An unloaded tape reports stopped too, so this
# only checks once a tape has been loaded.
class StopAtTapeEnd(Device):
    def __init__(self) -> None:
        self.__tape_loaded = False

    def on_event(self, event: DeviceEvent, devices: Dispatcher) -> None:
        if isinstance(event, LoadTape):
            self.__tape_loaded = True
        elif self.__tape_loaded and isinstance(event, TimeAdvanced):
            stopped = IsTapePlayerStopped()
            devices.notify(stopped)
            if stopped.stopped:
                self.__tape_loaded = False
                raise EmulationExit()


# Captures the machine as a 48K snapshot: the core's capture is
# typed by construction, so this only wraps it into the machine
# composition.
def capture_spectrum48(core: Core) -> Spectrum48Snapshot:
    captured = core.take_snapshot()
    assert isinstance(captured, Spectrum48CoreSnapshot)
    return Spectrum48Snapshot(core=captured)
