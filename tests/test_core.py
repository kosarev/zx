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
from zx._core import Core
from zx._core import CoreSnapshot
from zx._core import RunEvents
from zx._device import Device
from zx._device import DeviceEvent
from zx._device import Dispatcher
from zx._device import ReadPort


def test_on_input_propagates_exception() -> None:
    # An exception raised while handling a port read must propagate
    # out of the run promptly, aborting the input instruction just
    # like a deferred read, so nothing is committed on a value that
    # never existed.
    class _PortError(Exception):
        pass

    class _Raiser(Device):
        def on_event(self, event: DeviceEvent, devices: Dispatcher) -> None:
            if isinstance(event, ReadPort):
                raise _PortError()

    mach = zx.Core()
    dispatcher = Dispatcher([mach, _Raiser()])

    mach.write(0x8000, b'\xdb\xfe')  # IN A, (0xfe)
    mach.pc = 0x8000
    mach.a = 0x12

    with pytest.raises(_PortError):
        mach._run(dispatcher)

    assert mach.pc == 0x8000
    assert mach.ticks_since_int == 0
    assert mach.r == 0
    assert mach.a == 0x12


def test_on_output_propagates_exception() -> None:
    # An exception raised while handling a port write must propagate
    # out of the run promptly. Unlike an input, the write cannot be
    # aborted, so the instruction completes before the run stops.
    class _PortError(Exception):
        pass

    def raise_on_output(addr: int, value: int) -> None:
        raise _PortError()

    mach = zx.Core()
    dispatcher = Dispatcher([mach])
    mach.set_on_output_callback(raise_on_output)

    mach.write(0x8000, b'\xd3\xfe')  # OUT (0xfe), A
    mach.pc = 0x8000

    with pytest.raises(_PortError):
        mach._run(dispatcher)

    assert mach.pc == 0x8002
    assert mach.ticks_since_int == 11


def test_deferred_input() -> None:
    # A device that cannot tell the value of a port read yet defers
    # it: the input instruction is aborted with nothing committed and
    # the run ends, so a later run can retry the instruction once the
    # value is known.
    class _Port(Device):
        def __init__(self) -> None:
            self.ready = False
            self.num_read_attempts = 0

        def on_event(self, event: DeviceEvent, devices: Dispatcher) -> None:
            if isinstance(event, ReadPort):
                self.num_read_attempts += 1
                if self.ready:
                    event.supply(0x5a)
                else:
                    event.value = None

    mach = zx.Core()
    port = _Port()
    dispatcher = Dispatcher([mach, port])

    mach.write(0x8000, b'\xdb\xfe')  # IN A, (0xfe)
    mach.pc = 0x8000
    mach.a = 0x12

    # Stop as soon as the instruction completes. Aborted attempts do
    # not count toward the limit, nor do they report hitting it.
    mach.m1_fetches_to_stop = 1

    # The deferred read aborts and rolls back the instruction: no
    # time passes, no fetches counted, nothing written.
    events = RunEvents(mach._run(dispatcher))
    assert events == RunEvents.RETRY_INPUT
    assert port.num_read_attempts == 1
    assert mach.pc == 0x8000
    assert mach.ticks_since_int == 0
    assert mach.r == 0
    assert mach.a == 0x12

    # A further run re-poses the read for free.
    events = RunEvents(mach._run(dispatcher))
    assert events == RunEvents.RETRY_INPUT
    assert port.num_read_attempts == 2
    assert mach.pc == 0x8000
    assert mach.ticks_since_int == 0
    assert mach.r == 0
    assert mach.a == 0x12

    # Once the value is known, the retried instruction completes,
    # with the counters seeing a single execution.
    port.ready = True
    events = RunEvents(mach._run(dispatcher))
    assert events == RunEvents.FETCHES_LIMIT_HIT
    assert port.num_read_attempts == 3
    assert mach.pc == 0x8002
    assert mach.ticks_since_int == 11
    assert mach.r == 1
    assert mach.a == 0x5a


def test_from_snapshot() -> None:
    mach = zx.Core()
    mach.pc = 0x1234
    mach.hl = 0xbeef
    core_slice = next(d for _, d in mach.to_snapshot()
                      if isinstance(d, CoreSnapshot))

    clone = Core.from_snapshot(core_slice)
    assert (clone.pc, clone.hl) == (0x1234, 0xbeef)

    # The generic entry resolves the device type by the snapshot
    # type.
    device = Device.from_snapshot(core_slice)
    assert isinstance(device, Core)
    assert device.pc == 0x1234
