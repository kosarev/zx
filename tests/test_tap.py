#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.


import zx
from zx._device import CollectPortReads
from zx._device import Dispatcher
from zx._device import LoadTape
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


def test_tape_declares_its_port() -> None:
    # A tape drives the EAR bit of reads with A0 low; the
    # declaration alone, with no samples, keeps those reads on the
    # ReadPort path. With no tape loaded there is no signal to
    # drive, so nothing is declared.
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
