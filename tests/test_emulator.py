#!/usr/bin/env python3

# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.

import zx
from zx._device import DestroyEmulator
from zx._device import Device
from zx._device import DeviceEvent
from zx._device import Dispatcher
from zx._device import InitEmulator
from zx._spectrum import RunEvents


def test_basic() -> None:
    # Create an emulator instance.
    with zx.Emulator(headless=True) as mach:
        pass


def test_ticks_limit() -> None:
    # A tick limit stops the run between instructions, just past the
    # limit (no sub-instruction execution), without ending the frame —
    # the basis of sub-frame quanta. This also guards the packed-state
    # field alignment that exposes ticks_to_stop. A bare core suffices:
    # the tick limit is a core concern, no device set or container.
    mach = zx.Spectrum()
    dispatcher = Dispatcher([mach])
    frame_ticks = 69888

    mach.ticks_limit = 1000
    events = RunEvents(mach._run(dispatcher))
    assert RunEvents.END_OF_FRAME not in events
    assert 1000 <= mach.ticks_since_int < frame_ticks

    # With no limit the quantum runs on to the frame end.
    mach.ticks_limit = 0
    events = RunEvents(mach._run(dispatcher))
    assert RunEvents.END_OF_FRAME in events
    assert mach.ticks_since_int >= frame_ticks


def test_extra_devices() -> None:
    # Devices the caller attaches are added to the device set.
    extra = Device()
    with zx.Emulator(headless=True, extra_devices=[extra]) as mach:
        assert extra in list(mach)


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
    with zx.Emulator(headless=True, extra_devices=[recorder]):
        assert recorder.inited
        assert not recorder.destroyed
    assert recorder.destroyed
