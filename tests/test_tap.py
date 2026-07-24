#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.


import zx
from zx._device import CollectPortReads
from zx._device import Device
from zx._device import DeviceEvent
from zx._device import Dispatcher
from zx._device import IsTapePlayerStopped
from zx._device import LoadTape
from zx._device import PauseUnpauseTape
from zx._device import ReadPort
from zx._device import StopQuantum
from zx._tape import TapePlayer
from zx._time import Time


def test_basic() -> None:
    # Create a TAP file object.
    zx._tap.TAPFile(blocks=[b'abc', b'def'])

    # Parse a TAP file.
    data = b'123'
    block = len(data).to_bytes(2, 'little') + data
    format = zx._tap.TAPFile
    assert format.FORMAT_NAME == 'TAP'
    tap = format.decode('file.tap', block)

    # Generate pulses.
    tuple(tap.get_pulses())

    # Dump.
    assert 'TAPFile' in tap.dumps()


def test_tape_plays_to_the_end() -> None:
    # Reads pull the tape signal until the last pulse is fetched:
    # the tape then reports itself stopped, asks the run to stop
    # exactly once, and leaves further reads alone.
    class _StopObserver(Device):
        def __init__(self) -> None:
            self.count = 0

        def on_event(self, event: DeviceEvent,
                     devices: Dispatcher) -> None:
            if isinstance(event, StopQuantum):
                self.count += 1

    tape = TapePlayer()
    observer = _StopObserver()
    devices = Dispatcher([tape, observer])

    data = b'123'
    block = len(data).to_bytes(2, 'little') + data
    tape.on_event(LoadTape(zx._tap.TAPFile.decode('file.tap', block)),
                  devices)
    tape.on_event(PauseUnpauseTape(False), devices)

    stopped = IsTapePlayerStopped()
    tape.on_event(stopped, devices)
    assert not stopped.stopped

    # A read far past the whole recording exhausts the tape.
    read = ReadPort(0xfe, Time(10 ** 9, ticks_per_second=3_500_000))
    tape.on_event(read, devices)
    assert read.value == 0xbf
    assert observer.count == 1

    stopped = IsTapePlayerStopped()
    tape.on_event(stopped, devices)
    assert stopped.stopped

    # An ended tape drives nothing.
    read = ReadPort(0xfe, Time(2 * 10 ** 9, ticks_per_second=3_500_000))
    tape.on_event(read, devices)
    assert read.value == 0xff
    assert observer.count == 1


def test_tape_supplies_empty_series() -> None:
    # A tape drives the EAR bit of reads with A0 low; the empty
    # series, stating the addresses with no samples, keeps those
    # reads on the ReadPort path. With no tape loaded there is no
    # signal to drive, so nothing is supplied.
    def collect(tape: TapePlayer) -> CollectPortReads:
        event = CollectPortReads(Time(0, ticks_per_second=1),
                                 Time(1, ticks_per_second=1))
        tape.on_event(event, Dispatcher())
        return event

    tape = TapePlayer()
    assert collect(tape).series == []

    data = b'123'
    block = len(data).to_bytes(2, 'little') + data
    tape.on_event(LoadTape(zx._tap.TAPFile.decode('file.tap', block)),
                  Dispatcher())
    (series,) = collect(tape).series
    assert (series.addr_mask, series.addr_value) == (0x0001, 0x0000)
    assert len(series.ticks) == 0
