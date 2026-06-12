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
from zx._device import Device
from zx._spectrum import RunEvents


def test_basic() -> None:
    # Create an emulator instance.
    with zx.Spectrum(headless=True) as mach:
        pass


def test_ticks_limit() -> None:
    # A tick limit stops the run between instructions, just past the
    # limit (no sub-instruction execution), without ending the frame —
    # the basis of sub-frame quanta. This also guards the packed-state
    # field alignment that exposes ticks_to_stop.
    with zx.Spectrum(headless=True) as mach:
        frame_ticks = 69888

        mach.ticks_limit = 1000
        events = RunEvents(mach._run())
        assert RunEvents.END_OF_FRAME not in events
        assert 1000 <= mach.ticks_since_int < frame_ticks

        # With no limit the quantum runs on to the frame end.
        mach.ticks_limit = 0
        events = RunEvents(mach._run())
        assert RunEvents.END_OF_FRAME in events
        assert mach.ticks_since_int >= frame_ticks


def test_extra_devices() -> None:
    # Devices the caller attaches are added to the device set.
    extra = Device()
    with zx.Spectrum(headless=True, extra_devices=[extra]) as mach:
        assert extra in list(mach.devices)
