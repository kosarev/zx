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
from zx._device import Device
from zx._device import DeviceEvent
from zx._device import Dispatcher
from zx._device import ReadPort


def test_on_input_propagates_exception() -> None:
    # An exception raised while handling a port read must propagate
    # out of the run, and promptly -- at the offending instruction,
    # not at the end of the frame.
    class _PortError(Exception):
        pass

    class _Raiser(Device):
        def on_event(self, event: DeviceEvent, devices: Dispatcher) -> None:
            if isinstance(event, ReadPort):
                raise _PortError()

    mach = zx.Spectrum()
    dispatcher = Dispatcher([mach, _Raiser()])

    mach.write(0x8000, b'\xdb\xfe')  # IN A, (0xfe)
    mach.pc = 0x8000

    with pytest.raises(_PortError):
        mach._run(dispatcher)

    assert mach.ticks_since_int < 100
