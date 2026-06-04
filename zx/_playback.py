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

All recording formats (.rzx, etc.) will eventually translate into
UnifiedPlayback for internal use. The player will be reworked
accordingly. Format-specific types (RZXFile, etc.) remain as literal
representations for binary-exact roundtripping.


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

if typing.TYPE_CHECKING:  # TODO
    from ._spectrum import SpectrumState


# TODO: Rework to a time machine interface.
class PlaybackPlayer(Device):
    def __init__(self, machine: 'SpectrumState') -> None:
        super().__init__()
        self.__machine = machine
        self._playback: UnifiedPlayback | None = None

        self.playback_sample_values: bytes = b''
        self.playback_sample_i = 0

        self.samples: typing.Iterable[str | int] | None = None

    @property
    def is_active(self) -> bool:
        return self._playback is not None

    @property
    def is_spin_v05(self) -> bool:
        return self._playback is not None and self._playback.is_spin_v05

    def load(self, playback: UnifiedPlayback) -> None:
        self._playback = playback
        self.playback_sample_values = b''
        self.playback_sample_i = 0
        self.samples = self.__get_playback_samples()

    def unload(self) -> None:
        self._playback = None
        self.samples = None

    def __gen_segments(self) -> typing.Iterator[UnifiedPlaybackSegment]:
        assert self._playback is not None
        for seg in self._playback.segments:
            self.__machine.install_snapshot(seg.snapshot)
            yield seg

    def __gen_frames(self,
                     segments: typing.Iterator[UnifiedPlaybackSegment],
                     ) -> typing.Iterator[UnifiedPlaybackFrame]:
        for seg in segments:
            for frame in seg.frames:
                self.__machine.fetches_limit = frame.num_fetches
                yield frame

    def __gen_samples(self, frame: UnifiedPlaybackFrame
                      ) -> typing.Iterator[int]:
        yield from frame.port_samples.data

    def __get_playback_samples(self) -> typing.Iterable[str | int]:
        self.playback_sample_values = b''
        self.playback_sample_i = 0

        for frame in self.__gen_frames(self.__gen_segments()):
            samples = frame.port_samples.data

            yield 'START_OF_FRAME'

            for sample_i, sample in enumerate(self.__gen_samples(frame)):
                self.playback_sample_values = samples
                self.playback_sample_i = sample_i
                yield sample

            yield 'END_OF_FRAME'
