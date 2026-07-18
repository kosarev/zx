#!/usr/bin/env python3

# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.

import pytest

import zx
from zx._core import CoreSnapshot
from zx._core import RunEvents
from zx._core import Z80Snapshot
from zx._data import MachineSnapshot
from zx._device import DestroyEmulator
from zx._device import Device
from zx._device import DeviceEvent
from zx._device import Dispatcher
from zx._device import InitEmulator
from zx._error import Error


def test_basic() -> None:
    # Create an emulator instance.
    with zx.Emulator(headless=True):
        pass


def test_128k_emulator() -> None:
    from zx._data import Spectrum128
    from zx._resources import RESOURCES
    from zx._spectrum128 import Spectrum128MemoryMapping
    from zx._spectrum128 import Spectrum128Snapshot

    rom = (RESOURCES / 'roms' / 'Spectrum128.rom').read_bytes()

    # A 128K emulator constructs with both ROMs in their pages.
    with zx.Emulator(headless=True, model=Spectrum128,
                     snapshot=Spectrum128Snapshot()) as app:
        core = next(d for d in app.devices if isinstance(d, zx.Core))
        assert core.read(Spectrum128MemoryMapping(rom_page=0),
                         0x0000, 0x4000) == rom[:0x4000]
        assert core.read(Spectrum128MemoryMapping(rom_page=1),
                         0x0000, 0x4000) == rom[0x4000:]


def test_ticks_limit() -> None:
    # A tick limit stops the run between instructions, just past the
    # limit (no sub-instruction execution), without ending the frame —
    # the basis of sub-frame quanta. This also guards the packed-state
    # field alignment that exposes ticks_to_stop. A bare core suffices:
    # the tick limit is a core concern, no device set or container.
    mach = zx.Core()
    dispatcher = Dispatcher([mach])
    frame_ticks = 69888

    mach.ticks_to_stop = 1000
    events = RunEvents(mach._run(dispatcher))
    assert RunEvents.END_OF_FRAME not in events
    assert 1000 <= mach.ticks_since_int < frame_ticks

    # With no limit the quantum runs on to the frame end.
    mach.ticks_to_stop = 0
    events = RunEvents(mach._run(dispatcher))
    assert RunEvents.END_OF_FRAME in events
    assert mach.ticks_since_int >= frame_ticks


def test_extra_environment() -> None:
    # Devices the caller attaches are added to the device set.
    extra = Device()
    with zx.Emulator(headless=True, extra_environment=[extra]) as mach:
        assert extra in mach.devices


def test_init_and_destroy_emulator_dispatched() -> None:
    # Entering the emulator context instructs the devices to init;
    # leaving it instructs them to destroy.
    class _Recorder(Device):
        def __init__(self) -> None:
            self.inited = False
            self.destroyed = False

        def on_event(self, event: DeviceEvent,
                     devices: Dispatcher) -> None:
            if isinstance(event, InitEmulator):
                self.inited = True
            elif isinstance(event, DestroyEmulator):
                self.destroyed = True

    recorder = _Recorder()
    with zx.Emulator(headless=True, extra_environment=[recorder]):
        assert recorder.inited
        assert not recorder.destroyed
    assert recorder.destroyed


def test_load_installs_snapshot() -> None:
    snapshot = MachineSnapshot(core=CoreSnapshot(z80=Z80Snapshot(pc=0x1234)))

    # Loading installs the state into the persistent device set: the
    # set is the machine definition's fact, never the snapshot's.
    with zx.Emulator(headless=True) as app:
        old_devices = dict(app.machine.devices)
        old_environment = list(app.environment)
        app._load_snapshot(snapshot)

        assert app.machine.devices == old_devices
        assert app.environment == old_environment

        core = app.machine.devices['core']
        assert isinstance(core, zx.Core)
        assert core.pc == 0x1234

        # This snapshot activates nothing, so the keyboard is at
        # reset: inactive.
        assert not app.machine.devices['keyboard'].active


def test_construction_installs_snapshot() -> None:
    # Construction installs the given snapshot, the stock 48K one by
    # default -- which is what activates the machine's members.
    with zx.Emulator(headless=True) as app:
        assert app.machine.devices['core'].active
        assert app.machine.devices['keyboard'].active


def test_snapshot_addressing() -> None:
    # A machine snapshot addressing a device that is not in the
    # machine is a load error.
    with zx.Emulator(headless=True) as app:
        with pytest.raises(Error) as exc_info:
            app._load_snapshot(MachineSnapshot(core2=CoreSnapshot()))
        assert exc_info.value.id == 'unknown_device_in_snapshot'
