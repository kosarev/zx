# -*- coding: utf-8 -*-

#   ZX Spectrum Emulator.
#   https://github.com/kosarev/zx
#
#   Copyright (C) 2017-2026 Ivan Kosarev.
#   mail@ivankosarev.com
#
#   Published under the MIT license.

"""
This module implements the playback player for input recordings.

All recording formats (.rzx, etc.) translate into UnifiedPlayback for
internal use. Format-specific types (RZXFile, etc.) remain as literal
representations for binary-exact roundtripping.


Contracts
==========

PlaybackPlayer's responsibility is to issue the correct events needed
for a correct emulator to reproduce a recorded execution. It must not
reach into live machine state to compensate for quirks of particular
recording tools.

UnifiedPlayback is the canonical, correct execution-reproduction
material. Conversion from a format-specific type (e.g. RZXFile) must
produce a correct UnifiedPlayback. If the source recording does not
fully conform to the format (e.g. some recordings produced by SPIN
v0.5), any deviation must be corrected during conversion or as a
separate recovery operation — not patched at playback time. The
proper recovery procedure is: detect the non-conforming recording,
run it through a private headless Spectrum to determine the correct
frames, and emit a corrected UnifiedPlayback. The player then
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

  class UnifiedPlaybackSegment:
      key_frame: UnifiedSnapshot  # full machine state; ticks_since_int
                                  # serves as first_tick — no separate
                                  # field needed
      frames: list[UnifiedFrame]  # num_fetches + port_samples per frame

  class UnifiedPlayback:
      segments: list[UnifiedPlaybackSegment]

Key frames are critical for fast rollback: stepping back one frame from
30 minutes of recorded time requires replaying from the nearest key
frame. Key frame spacing is a critical design parameter.
"""

import typing
from ._data import UnifiedPlayback
from ._data import UnifiedPlaybackFrame
from ._data import UnifiedPlaybackSegment
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


# TODO: Rework to a time machine interface.
class PlaybackPlayer(Device):
    def __init__(self) -> None:
        super().__init__()
        self._playback: UnifiedPlayback | None = None
        self.__segments: typing.Iterator[UnifiedPlaybackSegment] = iter(())
        self.__frames: typing.Iterator[UnifiedPlaybackFrame] = iter(())
        self.__samples: typing.Iterator[int] | None = None
        self.__sample_count = 0

        self.playback_sample_values: bytes = b''
        self.playback_sample_i = 0

    @property
    def is_active(self) -> bool:
        return self._playback is not None

    @property
    def is_spin_v05(self) -> bool:
        return self._playback is not None and self._playback.is_spin_v05

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
        self.playback_sample_values = frame.port_samples.data
        self.__samples = iter(frame.port_samples.data)
        self.__sample_count = 0
        self.playback_sample_i = 0

    def __load(self, playback: UnifiedPlayback, devices: Dispatcher) -> None:
        self._playback = playback
        self.__segments = iter(playback.segments)
        self.__frames = iter(())
        self.__get_next_frame(devices)

    def __unload(self) -> None:
        self._playback = None
        self.__segments = iter(())
        self.__frames = iter(())
        self.__samples = None
        self.__sample_count = 0

    def on_event(self, event: DeviceEvent, devices: Dispatcher,
                 result: typing.Any) -> typing.Any:
        if isinstance(event, StartPlayback):
            self.__load(event.playback, devices)
            return result

        if isinstance(event, StopPlayback):
            self.__unload()
            return result

        if not self.is_active:
            return result

        if isinstance(event, ReadPort):
            assert self.__samples is not None
            sample = next(self.__samples, None)
            if sample is None:
                raise Error('Too few input samples.',
                            id='too_few_input_samples')
            self.__sample_count += 1
            self.playback_sample_i = self.__sample_count - 1
            return result & sample

        if isinstance(event, FetchesLimitHit):
            if self.__sample_count < len(self.playback_sample_values):
                raise Error('Too many input samples.',
                            id='too_many_input_samples')
            self.__get_next_frame(devices)
            devices.notify(EndOfFrame())

        return result
