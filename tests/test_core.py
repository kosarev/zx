#!/usr/bin/env python3

# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.

import numpy
import numpy.typing
import pytest

from zx._core import Core
from zx._core import CoreSnapshot
from zx._core import MemorySnapshot
from zx._core import RunEvents
from zx._core import Z80Snapshot
from zx._data import PortReadSeries
from zx._device import CollectPortReads
from zx._device import Device
from zx._device import DeviceEvent
from zx._device import Dispatcher
from zx._device import NewPortReads
from zx._device import RunQuantum
from zx._spectrum48 import Spectrum48Core
from zx._time import Time


def test_on_input_propagates_exception() -> None:
    # An exception raised in a custom port-read callback -- the
    # option for private rigs -- must propagate out of the run
    # promptly, aborting the input instruction just like a deferred
    # read, so nothing is committed on a value that never existed.
    class _PortError(Exception):
        pass

    def raise_on_input(addr: int, devices: Dispatcher) -> int | None:
        raise _PortError()

    mach = Spectrum48Core()
    dispatcher = Dispatcher([mach])
    mach.set_on_input_callback(raise_on_input)

    # The rig states a driver for every port, so reads the samples
    # do not resolve reach the callback.
    mach._add_port_read_samples(0, 1, 0, 0x0000, 0x0000, 0,
                                numpy.zeros(0, dtype=numpy.uint64))

    mach.write(0x8000,
               b'\xdb\xfe')  # IN A, (0xfe)
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

    mach = Spectrum48Core()
    dispatcher = Dispatcher([mach])
    mach.set_on_output_callback(raise_on_output)

    mach.write(0x8000,
               b'\xd3\xfe')  # OUT (0xfe), A
    mach.pc = 0x8000

    with pytest.raises(_PortError):
        mach._run(dispatcher)

    assert mach.pc == 0x8002
    assert mach.ticks_since_int == 11


def test_deferred_input() -> None:
    # A custom port-read callback that cannot tell the value yet
    # defers the read: the input instruction is aborted with nothing
    # committed and the run ends, so a later run can retry the
    # instruction once the value is known.
    class _Port:
        def __init__(self) -> None:
            self.ready = False
            self.num_read_attempts = 0

        def read(self, addr: int, devices: Dispatcher) -> int | None:
            self.num_read_attempts += 1
            return 0x5a if self.ready else None

    mach = Spectrum48Core()
    port = _Port()
    dispatcher = Dispatcher([mach])
    mach.set_on_input_callback(port.read)

    # The rig states a driver for every port, so reads the samples
    # do not resolve reach the callback.
    mach._add_port_read_samples(0, 1, 0, 0x0000, 0x0000, 0,
                                numpy.zeros(0, dtype=numpy.uint64))

    mach.write(0x8000,
               b'\xdb\xfe')  # IN A, (0xfe)
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


def test_disabled_core() -> None:
    # A disabled core is indistinguishable from an absent one: it
    # runs no quanta.
    core = Spectrum48Core(disabled=True)
    devices = Dispatcher([core])
    rate = core._ticks_per_second

    quantum = RunQuantum(stop_after=Time(1000, ticks_per_second=rate))
    devices.notify(quantum)
    assert quantum.advanced_ceiling is None

    core.disabled = False
    quantum = RunQuantum(stop_after=Time(1000, ticks_per_second=rate))
    devices.notify(quantum)
    assert quantum.advanced_ceiling is not None


def test_core_disabled_in_snapshots() -> None:
    from zx._spectrum48 import Spectrum48Core

    # The disabled flag is captured as the difference from the reset
    # state and applied by snapshot installs.
    core = Spectrum48Core()
    assert 'disabled' not in core.take_snapshot().to_json()

    core.disabled = True
    assert core.take_snapshot().to_json()['disabled'] is True

    core.install_snapshot(CoreSnapshot(disabled=True))
    assert core.disabled

    core.install_snapshot(CoreSnapshot())
    assert not core.disabled


def test_install_snapshot() -> None:
    # Installing a snapshot brings the core exactly to the state the
    # snapshot describes: the canonical reset state amended by what
    # the snapshot mentions. An empty snapshot means the canonical
    # reset state itself.
    from zx._spectrum48 import Spectrum48Core

    mach = Spectrum48Core()
    canonical = mach.take_snapshot().to_json()

    mach.pc = 0x8000
    mach.bc = 0x1234
    mach.border_colour = 5
    mach.write(0x8000, b'\x01\x02\x03')
    mach.install_snapshot(CoreSnapshot())
    assert mach.take_snapshot().to_json() == canonical

    mach.bc = 0x1234
    mach.install_snapshot(CoreSnapshot(z80=Z80Snapshot(pc=0x8000)))
    state = mach.take_snapshot().to_json()
    assert state['z80']['pc'] == 0x8000
    state['z80']['pc'] = canonical['z80']['pc']
    assert state == canonical


def test_stock_rom() -> None:
    from zx._data import DataRecord
    from zx._spectrum48 import Spectrum48ROM

    rom = Spectrum48ROM()
    assert len(rom.data) == 0x4000

    # The type alone determines the content, so the node stores
    # nothing and loads back from the bare tag.
    assert rom.to_json() == {}
    loaded = DataRecord.from_json({'type': 'Spectrum48ROM'})
    assert isinstance(loaded, Spectrum48ROM)
    assert loaded.data == rom.data


def test_memory_image_size() -> None:
    from zx._spectrum48 import Spectrum48MemorySnapshot

    # The model type fixes the configuration, so its node does not
    # store it; a plain record states it as an ordinary field.
    assert Spectrum48MemorySnapshot.image_size == 0x10000
    assert 'image_size' not in Spectrum48MemorySnapshot().to_json()
    plain = MemorySnapshot(image_size=0x10000)
    assert plain.to_json()['image_size'] == 0x10000


def test_48k_memory() -> None:
    from zx._spectrum48 import Spectrum48Core
    from zx._spectrum48 import Spectrum48CoreSnapshot
    from zx._spectrum48 import Spectrum48MemorySnapshot
    from zx._spectrum48 import Spectrum48ROM

    ram = bytes(range(256)) * 192

    # An unstated ROM means the stock one.
    mach = Spectrum48Core()
    mach.install_snapshot(Spectrum48CoreSnapshot(
        memory=Spectrum48MemorySnapshot(ram=ram)))
    assert mach.read(0x0000, 0x10000) == Spectrum48ROM().data + ram

    # A stated ROM replaces the stock one.
    mach.install_snapshot(Spectrum48CoreSnapshot(
        memory=Spectrum48MemorySnapshot(rom=bytes(0x4000), ram=ram)))
    assert mach.read(0x0000, 0x10000) == bytes(0x4000) + ram


def test_typed_capture() -> None:
    from zx._spectrum48 import Spectrum48Core
    from zx._spectrum48 import Spectrum48CoreSnapshot
    from zx._spectrum48 import Spectrum48MemorySnapshot
    from zx._spectrum48 import Spectrum48ULASnapshot

    # The capture is typed by construction, its members included.
    core = Spectrum48Core()
    core.install_snapshot(Spectrum48CoreSnapshot())
    captured = core.take_snapshot()
    assert type(captured) is Spectrum48CoreSnapshot
    assert isinstance(captured.ula, Spectrum48ULASnapshot)
    assert isinstance(captured.memory, Spectrum48MemorySnapshot)

    # The stock ROM captures as absence, a deviated socket
    # explicitly.
    assert captured.memory.rom is None
    core.write(0x0000, b'\x12\x34')
    deviated = core.take_snapshot()
    assert isinstance(deviated, Spectrum48CoreSnapshot)
    rom = deviated.memory.rom
    assert rom is not None
    assert rom.data[:2] == b'\x12\x34'

    # The disabled flag is ordinary captured content.
    core.disabled = True
    assert core.take_snapshot().disabled is True


# The core's resolution: the CPU clock of the default 48K core.
CORE_RESOLUTION = 3_500_000


# Packs (tick, value) samples into series entry words.
def _sample_entries(
        *samples: tuple[int, int]) -> numpy.typing.NDArray[numpy.uint64]:
    return numpy.array([(tick << 8) | value for tick, value in samples],
                       dtype=numpy.uint64)


# A bare core about to execute IN A, (0xfe) with A = 0x12, so the
# port address is 0x12fe and the input cycle's read falls at tick
# 10. The JR loop then spins to the end of the frame, keeping the
# power-up memory pattern from executing as code.
def _make_core_reading_port() -> Core:
    core = Spectrum48Core()
    core.write(0x8000,
               b'\xdb\xfe'   # IN A, (0xfe)
               b'\x18\xfe')  # JR $
    core.pc = 0x8000
    core.a = 0x12
    return core


def test_port_read_samples_answer_covered_read() -> None:
    core = _make_core_reading_port()
    devices = Dispatcher([core])

    core._add_port_read_samples(
        0, CORE_RESOLUTION, 0, 0xffff, 0x12fe, 1000,
        _sample_entries((0, 0x55)))

    core._run(devices)
    assert core.a == 0x55


def test_port_read_samples_and_together() -> None:
    # Two series drive the same read; undriven bits stay 1s, so the
    # samples AND together like open-collector outputs.
    core = _make_core_reading_port()
    devices = Dispatcher([core])

    core._add_port_read_samples(
        0, CORE_RESOLUTION, 0, 0xffff, 0x12fe, 1000,
        _sample_entries((0, 0xfa)))
    core._add_port_read_samples(
        0, CORE_RESOLUTION, 0, 0xffff, 0x12fe, 1000,
        _sample_entries((0, 0xaf)))

    core._run(devices)
    assert core.a == 0xaa


def test_port_read_samples_cover_num_ticks() -> None:
    # A series covers num_ticks ticks from tick 0, the end excluded.
    # The IN's read falls at tick 10, so a 10-tick span misses it
    # and the read defers, with nothing committed.
    core = _make_core_reading_port()
    devices = Dispatcher([core])

    core._add_port_read_samples(
        0, CORE_RESOLUTION, 0, 0xffff, 0x12fe, 10,
        _sample_entries((0, 0x55)))

    events = RunEvents(core._run(devices))
    assert RunEvents.RETRY_INPUT in events
    assert core.pc == 0x8000
    assert core.a == 0x12

    # An 11-tick span covers it.
    core = _make_core_reading_port()
    devices = Dispatcher([core])

    core._add_port_read_samples(
        0, CORE_RESOLUTION, 0, 0xffff, 0x12fe, 11,
        _sample_entries((0, 0x55)))

    core._run(devices)
    assert core.a == 0x55


def test_port_read_with_no_matching_series_is_open_bus() -> None:
    # With no series matching the address, no device drives the
    # read: the input lines all read high. A bare core with no
    # samples at all reads every port that way.
    core = _make_core_reading_port()
    devices = Dispatcher([core])

    core._run(devices)
    assert core.a == 0xff

    core = _make_core_reading_port()
    devices = Dispatcher([core])

    core._add_port_read_samples(
        0, CORE_RESOLUTION, 0, 0xffff, 0x30fe, 1000,
        _sample_entries((0, 0x55)))

    core._run(devices)
    assert core.a == 0xff


def test_empty_series_defers_the_read() -> None:
    # An empty series states its device can foretell nothing, so
    # reads of its addresses cannot be resolved from the samples,
    # whatever other series cover: they defer.
    core = _make_core_reading_port()
    devices = Dispatcher([core])

    core._add_port_read_samples(
        0, CORE_RESOLUTION, 0, 0xffff, 0x12fe, 1000,
        _sample_entries((0, 0x55)))
    core._add_port_read_samples(
        0, 1, 0, 0x0000, 0x0000, 0,
        numpy.zeros(0, dtype=numpy.uint64))

    events = RunEvents(core._run(devices))
    assert RunEvents.RETRY_INPUT in events
    assert core.pc == 0x8000
    assert core.a == 0x12


def test_port_read_samples_in_device_resolution() -> None:
    # A series at twice the core resolution: the read at core tick
    # 10 is at device tick 20 exactly, so a sample since device
    # tick 20 drives it and a 21-device-tick span covers it.
    core = _make_core_reading_port()
    devices = Dispatcher([core])

    core._add_port_read_samples(
        0, 2 * CORE_RESOLUTION, 0, 0xffff, 0x12fe, 21,
        _sample_entries((0, 0x55), (20, 0x66)))

    core._run(devices)
    assert core.a == 0x66

    # A sample since device tick 21 starts right after the read.
    core = _make_core_reading_port()
    devices = Dispatcher([core])

    core._add_port_read_samples(
        0, 2 * CORE_RESOLUTION, 0, 0xffff, 0x12fe, 1000,
        _sample_entries((0, 0x55), (21, 0x66)))

    core._run(devices)
    assert core.a == 0x55

    # A 20-device-tick span ends exactly at the read, deferring it.
    core = _make_core_reading_port()
    devices = Dispatcher([core])

    core._add_port_read_samples(
        0, 2 * CORE_RESOLUTION, 0, 0xffff, 0x12fe, 20,
        _sample_entries((0, 0x55)))

    events = RunEvents(core._run(devices))
    assert RunEvents.RETRY_INPUT in events
    assert core.a == 0x12


def test_port_read_samples_progress_with_reads() -> None:
    # Two reads pick their values from the sample series as time
    # progresses: IN A, (0xfe); LD C, A; IN A, (0xfe) reads at
    # ticks 10 and 25, with the sampled value changing at tick 20.
    core = Spectrum48Core()
    core.write(0x8000,
               b'\xdb\xfe'   # IN A, (0xfe)
               b'\x4f'       # LD C, A
               b'\xdb\xfe'   # IN A, (0xfe)
               b'\x18\xfe')  # JR $
    core.pc = 0x8000
    core.a = 0x12
    devices = Dispatcher([core])

    core._add_port_read_samples(
        0, CORE_RESOLUTION, 0, 0x00ff, 0x00fe, 1000,
        _sample_entries((0, 0x55), (20, 0x66)))

    core._run(devices)
    # TODO: Use the c accessor once CoreState grows the 8-bit
    # register accessors.
    assert core.bc & 0xff == 0x55
    assert core.a == 0x66


def test_port_read_samples_replaced_wholesale() -> None:
    # Clearing discards previously added series entirely.
    core = _make_core_reading_port()
    devices = Dispatcher([core])

    core._add_port_read_samples(
        0, CORE_RESOLUTION, 0, 0xffff, 0x12fe, 1000,
        _sample_entries((0, 0x55)))
    core._clear_port_read_samples()
    core._add_port_read_samples(
        0, CORE_RESOLUTION, 0, 0xffff, 0x12fe, 1000,
        _sample_entries((0, 0x66)))

    core._run(devices)
    assert core.a == 0x66


def test_new_port_reads_load_the_samples() -> None:
    # A published series answers the read via the border: the
    # core loads its C++-side copy on NewPortReads.
    core = _make_core_reading_port()
    devices = Dispatcher([core])

    series = PortReadSeries(
        addr_mask=0xffff, addr_value=0x12fe,
        ticks_per_second=CORE_RESOLUTION,
        ticks=numpy.array([0], dtype=numpy.uint64),
        values=numpy.array([0x55], dtype=numpy.uint64),
        end_tick=1000)
    devices.notify(NewPortReads(
        Time(0, ticks_per_second=CORE_RESOLUTION), [series]))

    core._run(devices)
    assert core.a == 0x55


def test_new_port_reads_replace_the_samples_wholesale() -> None:
    # A publication replaces the samples entirely: series added
    # beforehand are gone, so only the published statements drive
    # the ports.
    core = _make_core_reading_port()
    devices = Dispatcher([core])

    core._add_port_read_samples(
        0, CORE_RESOLUTION, 0, 0xffff, 0x12fe, 1000,
        _sample_entries((0, 0x55)))
    devices.notify(NewPortReads(
        Time(0, ticks_per_second=CORE_RESOLUTION), []))

    core._run(devices)
    assert core.a == 0xff


def test_new_port_reads_relate_the_resolutions() -> None:
    # A series on its own timeline at twice the core resolution,
    # collected for a floor at core tick 5, so tick 0 is device
    # tick 10: the history before it prunes down to the sample in
    # effect there, and the change at device tick 30 lies past the
    # read at core tick 10.
    core = _make_core_reading_port()
    devices = Dispatcher([core])

    series = PortReadSeries(
        addr_mask=0xffff, addr_value=0x12fe,
        ticks_per_second=2 * CORE_RESOLUTION,
        ticks=numpy.array([0, 8, 30], dtype=numpy.uint64),
        values=numpy.array([0x11, 0x55, 0x66], dtype=numpy.uint64),
        end_tick=1000)
    devices.notify(NewPortReads(
        Time(5, ticks_per_second=CORE_RESOLUTION), [series]))

    core._run(devices)
    assert core.a == 0x55


# A supplier of the value in effect at the floor, one tick of
# coverage: any read past it defers and is answered at the next
# collect. A None value means the device supplies the empty series
# alone.
class _FloorValueSupplier(Device):
    def __init__(self, value: int | None) -> None:
        self.__value = value

    def on_event(self, event: DeviceEvent, devices: Dispatcher) -> None:
        if isinstance(event, CollectPortReads):
            assert event.floor.ticks_per_second == CORE_RESOLUTION
            floor_tick = event.floor.count

            if self.__value is None:
                event.supply(PortReadSeries(
                    addr_mask=0xffff, addr_value=0x12fe,
                    ticks_per_second=CORE_RESOLUTION,
                    ticks=numpy.zeros(0, dtype=numpy.uint64),
                    values=numpy.zeros(0, dtype=numpy.uint64)))
                return

            event.supply(PortReadSeries(
                addr_mask=0xffff, addr_value=0x12fe,
                ticks_per_second=CORE_RESOLUTION,
                ticks=numpy.array([floor_tick], dtype=numpy.uint64),
                values=numpy.array([self.__value], dtype=numpy.uint64),
                end_tick=floor_tick + 1))


# One hand-driven quantum of the loop's dispatches: collect, publish,
# run. Returns the position the run reports.
def _run_one_quantum(devices: Dispatcher, floor: Time) -> Time:
    collect = CollectPortReads(floor, floor)
    devices.notify(collect)
    devices.notify(NewPortReads(floor, collect.series))

    run = RunQuantum()
    devices.notify(run)
    assert run.advanced_floor is not None
    return run.advanced_floor


def test_deferred_read_resumes_on_the_floor_value() -> None:
    core = _make_core_reading_port()
    devices = Dispatcher([core, _FloorValueSupplier(0x55)])

    # The first quantum: the supplier's value at the floor covers
    # tick 0 only, so the read at tick 10 defers -- the instruction
    # aborts with the counters rewound, and the reported position
    # is the read's moment.
    floor = Time(0, ticks_per_second=CORE_RESOLUTION)
    position = _run_one_quantum(devices, floor)
    assert core.pc == 0x8000
    assert core.a == 0x12
    assert (position.count, position.ticks_per_second) == (
        10, CORE_RESOLUTION)

    # The next quantum starts at the read's moment, so the
    # supplier's value at the floor now covers it: the read
    # resumes and completes.
    _run_one_quantum(devices, position)
    assert core.a == 0x55


def test_deferred_read_defers_again_without_coverage() -> None:
    # A supplier saying nothing keeps deferring the read, with the
    # same position reported every time.
    core = _make_core_reading_port()
    devices = Dispatcher([core, _FloorValueSupplier(None)])

    floor = Time(0, ticks_per_second=CORE_RESOLUTION)
    position = _run_one_quantum(devices, floor)
    assert (position.count, position.ticks_per_second) == (
        10, CORE_RESOLUTION)

    position = _run_one_quantum(devices, position)
    assert (position.count, position.ticks_per_second) == (
        10, CORE_RESOLUTION)
    assert core.pc == 0x8000
    assert core.a == 0x12


def test_port_read_samples_validation() -> None:
    core = Spectrum48Core()
    no_entries = numpy.zeros(0, dtype=numpy.uint64)

    # The resolution must be positive and fit 32 bits.
    with pytest.raises(ValueError):
        core._add_port_read_samples(0, 0, 0, 0, 0, 0, no_entries)
    with pytest.raises(ValueError):
        core._add_port_read_samples(0, 1 << 32, 0, 0, 0, 0, no_entries)

    # The first entry must be at tick 0.
    with pytest.raises(ValueError):
        core._add_port_read_samples(
            0, CORE_RESOLUTION, 0, 0, 0, 10, _sample_entries((1, 0x55)))

    # An empty series covers no ticks.
    with pytest.raises(ValueError):
        core._add_port_read_samples(0, CORE_RESOLUTION, 0, 0, 0, 10,
                                    no_entries)
