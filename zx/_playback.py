#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.

"""
This module implements the playback player for input recordings.

All recording formats (.rzx, etc.) translate into MachinePlayback for
internal use. Format-specific types (RZXFile, etc.) remain as literal
representations for binary-exact roundtripping.


Contracts
==========

PlaybackPlayer's responsibility is to issue the correct events needed
for a correct emulator to reproduce a recorded execution. It must not
reach into live machine state to compensate for quirks of particular
recording tools.

MachinePlayback is the canonical, correct execution-reproduction
material. Conversion from a format-specific type (e.g. RZXFile) must
produce a correct MachinePlayback. If the source recording does not
fully conform to the format (e.g. some recordings produced by SPIN
v0.5), any deviation must be corrected during conversion or as a
separate recovery operation — not patched at playback time. The
proper recovery procedure is: detect the non-conforming recording,
run it through a private headless core to determine the correct
frames, and emit a corrected MachinePlayback. The player then
receives correct input and needs no format-specific knowledge.


Design: layered correction streams
===================================

The base layer follows the RZX model: fetch-count frame boundaries with
port samples for IN instructions. This is robust to T-state timing bugs
but not to instruction-level bugs (e.g. a wrong DAA flag update causes
a wrong branch, a different port-reading pattern, and desync).

Additional optional correction layers address this. Each layer is an
independent data stream. Emulators that do not understand a layer
ignore it gracefully — playback reliability degrades rather than fails.
Producers choose which layers to record, trading reliability against
file size.

Base layer (always present):
  Fetch-count frame boundaries + port samples (IN instruction responses).

Flag correction layer:
  A bit stream of conditional branch outcomes (taken/not taken = 1 bit
  each). The branch outcome implies the relevant flag value and corrects
  it in place, preventing errors from cascading. Based on def-use chains:
  a flag definition is only flushed to the trace when consumed by a
  conditional branch; definitions overwritten before use are discarded.
  Estimated overhead: ~20-50 bytes/frame for typical games.

Further layers for the R register, undocumented flag bits F3/F5 (XF/YF),
MEMPTR (WZ), block instruction flags, interrupt timing, etc. can be
added without breaking existing tools.


Def-use tracing principle
==========================

A value is only recorded at the point it is actually consumed by a use
that affects control flow.

- A register/flag write is a pending definition — not immediately
  recorded.
- If overwritten before being used, it is discarded (dead value).
- When a conditional branch consumes the value, the pending definition
  is flushed as the branch outcome (1 bit), which also corrects the
  flag in place.

This can be extended to memory: every instruction fetch is a use of that memory
cell. If the cell was previously written, the write is pending; the
fetch flushes it. Self-modifying code is handled automatically.


Self-correction and bug localisation
======================================

The trace serves as a correctness oracle during replay:

1. Reproducible playback: force the recorded branch outcome, steering
   the emulator onto the correct execution path.
2. Self-correction: correct the value at the use point, preventing
   errors from cascading into subsequent instructions.
3. Bug localisation: compare the emulator's computed value against the
   trace. A discrepancy identifies a bug; the def-use chain traces back
   to the originating instruction, reporting exactly which instruction
   behaves incorrectly and under what conditions.


Initial simplified design
===========================

A playback consists of segments, each starting from a known machine
state (key frame) followed by a sequence of frames:

  class MachinePlaybackSegment:
      key_frame: MachineSnapshot  # full machine state; ticks_since_int
                                  # serves as first_tick — no separate
                                  # field needed
      frames: list[MachinePlaybackFrame]  # num_fetches + port_samples

  class MachinePlayback:
      segments: list[MachinePlaybackSegment]

Key frames are critical for fast rollback: stepping back one frame from
30 minutes of recorded time requires replaying from the nearest key
frame. Key frame spacing is a critical design parameter.
"""

import typing

import numpy

from ._data import MachinePlayback
from ._data import MachinePlaybackFrame
from ._data import MachinePlaybackSegment
from ._data import PortReadSeries
from ._device import CollectPortReads
from ._device import Device
from ._device import DeviceEvent
from ._device import Dispatcher
from ._device import EndOfFrame
from ._device import FetchesLimitHit
from ._device import InstallSnapshot
from ._device import ReadPort
from ._device import SetFetchesLimit
from ._device import StartPlayback
from ._device import StopPlayback
from ._error import Error
from ._except import EmulationExit
from ._time import Time


# TODO: Rework to a time machine interface.
class PlaybackPlayer(Device):
    def __init__(self) -> None:
        super().__init__()
        self.__playback: MachinePlayback | None = None
        self.__segments: typing.Iterator[MachinePlaybackSegment] = iter(())
        self.__frames: typing.Iterator[MachinePlaybackFrame] = iter(())
        self.__sample_values: bytes = b''
        self.__sample_count = 0

        # True when a read has deferred and its sample is yet to be
        # dealt at the following collect.
        self.__deferred_read_pending = False

        # The moment of the dealt but not yet confirmed sample;
        # None when there is no such sample.
        self.__dealt_time: Time | None = None

    @property
    def is_spin_v05(self) -> bool:
        return self.__playback is not None and self.__playback.is_spin_v05

    @property
    def has_remaining_samples(self) -> bool:
        return self.__sample_count < len(self.__sample_values)

    def __get_next_segment(self, devices: Dispatcher) -> None:
        seg = next(self.__segments, None)
        if seg is None:
            devices.notify(StopPlayback())
            raise EmulationExit()

        devices.notify(InstallSnapshot(seg.snapshot))
        self.__frames = iter(seg.frames)

    def __get_next_frame(self, devices: Dispatcher) -> None:
        while True:
            frame = next(self.__frames, None)
            if frame is not None:
                break
            self.__get_next_segment(devices)

        devices.notify(SetFetchesLimit(frame.num_fetches))
        self.__sample_values = frame.port_samples.data
        self.__sample_count = 0

    def __load(self, playback: MachinePlayback, devices: Dispatcher) -> None:
        self.__playback = playback
        self.__segments = iter(playback.segments)
        self.__frames = iter(())
        self.__deferred_read_pending = False
        self.__get_next_frame(devices)

    def __unload(self) -> None:
        self.__playback = None
        self.__segments = iter(())
        self.__frames = iter(())
        self.__sample_values = b''
        self.__sample_count = 0
        self.__deferred_read_pending = False

    # A dealt sample counts consumed only on evidence that time
    # moved past its moment: the deferred read there is the first
    # thing the retry executes, so a later moment means it read the
    # sample -- while a read deferring at the same moment again
    # means another series blocked it, and the same sample is dealt
    # anew. With no moment given, the evidence is unconditional,
    # like a frame's fetch limit having been reached.
    def _confirm_dealt_sample(self, past: Time | None = None) -> None:
        if self.__dealt_time is None:
            return

        if past is None or self.__dealt_time < past:
            self.__sample_count += 1
            self.__dealt_time = None

    # Deals the recorded samples, one per deferred read, as a
    # one-tick series at the floor -- the deferred read's moment.
    # With no read deferred yet, the bare empty series makes the
    # next read defer first. The all-addresses pattern does double
    # duty: no read resolves behind the recording's back, and at
    # the sampled moment the recorded value ANDs with any live
    # series covering it, exactly as the ReadPort answers combined.
    def __supply_sample(self, event: CollectPortReads) -> None:
        self._confirm_dealt_sample(event.floor)

        if (not self.__deferred_read_pending or
                not self.has_remaining_samples):
            event.supply(PortReadSeries(addr_mask=0x0000,
                                        addr_value=0x0000))
            return

        sample = self.__sample_values[self.__sample_count]
        self.__deferred_read_pending = False
        self.__dealt_time = event.floor

        floor_tick = event.floor.count
        event.supply(PortReadSeries(
            addr_mask=0x0000, addr_value=0x0000,
            ticks_per_second=event.floor.ticks_per_second,
            ticks=numpy.array([floor_tick], dtype=numpy.uint64),
            values=numpy.array([sample], dtype=numpy.uint64),
            end_tick=floor_tick + 1))

    def on_event(self, event: DeviceEvent, devices: Dispatcher) -> None:
        if isinstance(event, StartPlayback):
            self.__load(event.playback, devices)
            return

        if isinstance(event, StopPlayback):
            self.__unload()
            return

        if self.__playback is None:
            return

        if isinstance(event, CollectPortReads):
            self.__supply_sample(event)
            return

        if isinstance(event, ReadPort):
            self._confirm_dealt_sample(event.time)

            if not self.has_remaining_samples:
                raise Error('Too few input samples.',
                            id='too_few_input_samples')

            # The read defers; the next collect deals the sample at
            # the read's moment, where the retry consumes it.
            event.value = None
            self.__deferred_read_pending = True
            return

        if isinstance(event, FetchesLimitHit):
            # Reaching the frame's fetch limit means the run went
            # past any dealt sample's moment.
            self._confirm_dealt_sample()

            if self.has_remaining_samples:
                raise Error('Too many input samples.',
                            id='too_many_input_samples')
            self.__get_next_frame(devices)
            devices.notify(EndOfFrame())


class PlaybackRecorder(Device):
    def __init__(self, *, disabled: bool = False) -> None:
        super().__init__(disabled=disabled)
        self.__segments: list[MachinePlaybackSegment] = []

    def make_playback(self) -> MachinePlayback:
        return MachinePlayback(segments=self.__segments)

    def on_event(self, event: DeviceEvent, devices: Dispatcher) -> None:
        if self.disabled:
            return

        if isinstance(event, InstallSnapshot):
            self.__segments.append(
                MachinePlaybackSegment(snapshot=event.snapshot))

        # TODO: Collect frames from OutputFrame events once the C++
        # core counts the executed reads and fetches itself -- reads
        # resolved from samples never reach ReadPort, so the frames
        # must come from the core's own stream.
